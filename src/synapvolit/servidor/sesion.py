"""Sesión del motor: fuente → decodificador → procesador → calibración → interfaz por WebSocket.

Diseño asíncrono en un solo hilo de eventos, con tres reglas para que nada bloquee la señal:

1. **La fuente y el bucle de procesamiento son tareas independientes.** La fuente entrega bytes
   en cuanto llegan; el bucle procesa todo lo pendiente cada ~10 ms. El trabajo de cada paso es
   corto (<3% de un núcleo), así que el bucle de eventos queda libre casi siempre.
2. **Las órdenes de la interfaz entran a una cola** y se aplican al inicio del siguiente paso.
   Un clic nunca ejecuta trabajo dentro del manejador de la conexión.
3. **Cada cliente tiene su propia cola de salida, acotada.** Si un cliente es lento, se descartan
   sus mensajes más viejos (los niveles se reenvían 30 veces por segundo); nunca se espera por él.

La frescura de la señal es la única regla que depende del reloj: si no llegan muestras nuevas en
250 ms, todo lo derivado se marca inválido aunque el último valor parezca bueno. El reloj se
inyecta, así que se prueba con tiempos exactos.
"""

from __future__ import annotations

import asyncio
import dataclasses
import os
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed

from ..clasificacion import Decisor
from ..procesamiento import ConfigProcesamiento, Procesador
from ..registro import cargar_perfil, frecuencia_mediana, guardar_perfil, raiz_por_defecto
from ..transporte import BufferCircular, Decodificador
from .bitacora import Bitacora
from .calibracion import CALCULANDO, LISTA, TERMINALES, MaquinaCalibracion
from .contrato import (
    ErrorOrden,
    leer_orden,
    m_calibracion,
    m_decodificador,
    m_error,
    m_estado,
    m_hola,
    m_niveles,
    m_osc,
    m_perfil,
    m_resultado,
    m_sesion,
)
from .osciloscopio import Osciloscopio


def abrir_en_explorador(carpeta: Path) -> None:
    """Abre la carpeta del paciente en el explorador del sistema (solo esa, nunca otra ruta)."""
    if sys.platform == "win32":
        os.startfile(carpeta)
    else:
        subprocess.run(
            ["open" if sys.platform == "darwin" else "xdg-open", str(carpeta)], check=False
        )


HOSTS_LOCALES = {"127.0.0.1", "localhost", "::1", "[::1]"}


def origen_permitido(origen: str | None) -> bool:
    """Solo páginas locales: evita que un sitio web cualquiera lea la sEMG desde el navegador.

    ``None`` es un cliente que no es navegador; ``"null"`` es un archivo abierto con ``file://``.
    """
    if origen in (None, "null"):
        return True
    partes = urlsplit(origen)
    return partes.scheme in ("http", "https") and (partes.hostname or "") in HOSTS_LOCALES


class Sesion:
    """Une todas las piezas del motor y las sirve por WebSocket."""

    PASO_S = 0.010
    NIVELES_S = 1 / 30
    ESTADO_S = 1.0
    CALIBRACION_S = 0.1
    FRESCURA_S = 0.25
    DECISION_S = 0.125  # 8 Hz, como el contrato original con el juego

    def __init__(
        self,
        fuente,
        *,
        cfg: ConfigProcesamiento | None = None,
        reloj: Callable[[], float] = time.monotonic,
        raiz_datos: Path | None = None,
        abridor: Callable[[Path], object] | None = None,
    ) -> None:
        self.fuente, self.reloj = fuente, reloj
        self.bita = Bitacora(raiz_datos or raiz_por_defecto(), reloj)
        self.osc: Osciloscopio | None = None
        self.suscritos: set[asyncio.Queue] = set()
        self._t_osc = -1e9
        self.perfil: tuple | None = None  # (matriz, modelo, info) del paciente de la sesión
        self._guardando: asyncio.Future | None = None
        self._guardando_codigo: str | None = None
        self._ultimo_codigo: str | None = None
        self.abridor = abridor or abrir_en_explorador
        self.cfg = cfg or ConfigProcesamiento(fs=fuente.fs or 2000.0)
        self.buf = BufferCircular(self.cfg.canales, int(4 * self.cfg.fs))
        self.dec = Decodificador(self.buf, fs=self.cfg.fs)
        self.proc = Procesador(self.cfg)
        self.cal = MaquinaCalibracion(self.cfg.canales, 1 / self.PASO_S)
        self.cal.calculo_externo = True
        self._calculo: asyncio.Future | None = None
        self.clientes: dict[ServerConnection, asyncio.Queue] = {}
        self.ordenes: list[tuple[asyncio.Queue | None, dict]] = []
        self.fresca = False
        self.clase_libre = 0
        self.decisor: Decisor | None = None
        self._t_dec = -1e9
        self.puerto_real: int | None = None
        self._ult_proc, self._t_dato = 0, -1e9
        self._t_niv = self._t_est = self._t_cal = -1e9
        self._estado_previo: tuple | None = None
        self._fase_previa = self.cal.fase

    # ---- núcleo síncrono: un paso del bucle (se prueba sin red ni reloj real) ----
    def paso(self, t: float) -> None:
        if self.dec.fs != self.cfg.fs:  # el brazalete anunció otro muestreo: se rehace la cadena
            self._rehacer(self.dec.fs)
        for cola, orden in self.ordenes:
            self._aplicar(cola, orden, t)
        self.ordenes.clear()
        p = self.proc
        p.actualizar(self.buf)
        nuevas = p.procesadas != self._ult_proc
        if nuevas:
            self._ult_proc, self._t_dato = p.procesadas, t
        self.fresca = t - self._t_dato < self.FRESCURA_S
        if (
            nuevas and self.decisor is not None
        ):  # una entrada al suavizado por paso con datos nuevos
            self.decisor.actualizar(p.rasgos, p.env_uv, p.rasgos_validos)
        cambio = self.cal.avanzar(
            t, p.env_uv, p.env_valida, p.calidad, self.fresca, p.rasgos, p.rasgos_validos
        )
        # el entrenamiento (~0.1 s) corre en un hilo: el bucle sigue procesando y publicando
        if self.cal.fase == CALCULANDO and self._calculo is None:
            self._calculo = asyncio.get_running_loop().run_in_executor(None, self.cal.calcular)
        if self._calculo is not None and self._calculo.done():
            resultado, self._calculo = self._calculo.result(), None
            cambio = self.cal.terminar(t, resultado) or cambio
        if cambio:
            self._t_cal = -1e9  # publicar el cambio de fase de inmediato
            if self.cal.fase == LISTA:
                p.matriz = self.cal.matriz
                if self.cal.modelo is not None:
                    self.decisor = Decisor(self.cal.modelo, self.cal.matriz)
                if self.bita.registro is not None:
                    ex = self.cal.modelo.exactitud if self.cal.modelo else None
                    self.bita.registro.anotar(
                        "calibracion",
                        modo=self.cal.modo,
                        exactitud=ex,
                        verificacion=self.cal.verificacion,
                    )
                    self._tras_calibrar()
            if self.cal.fase in TERMINALES:
                self._difundir(m_resultado(self.cal))
        if self._guardando is not None and self._guardando.done():
            fut, self._guardando = self._guardando, None
            try:
                fut.result()
                info = self.perfil[2] if self.perfil else None
                self._difundir(m_perfil(self._guardando_codigo, "guardado", info))
            except OSError as e:
                self._difundir(m_error(f"no se pudo guardar el perfil: {e}"))
        fin = self.bita.tick(t, bool(self.clientes))
        if fin is not None:
            self._difundir(m_sesion(fin[0], True, fin[1]))
        # el paciente simulado hace lo que pide la calibración, o lo último que pidió la interfaz
        self.fuente.pedir(
            self.cal.objetivo if self.cal.fase not in TERMINALES else self.clase_libre
        )
        self._publicar(t)

    def _aplicar(self, cola: asyncio.Queue | None, orden: dict, t: float) -> None:
        cmd = orden["cmd"]
        if cmd == "calibrar":
            if self.cal.fase not in TERMINALES or self._calculo is not None:
                return self._responder(cola, m_error("ya hay una calibración en curso"))
            verificar = None
            if orden["modo"] == "verificar":
                if self.perfil is None:
                    return self._responder(cola, m_error("no hay un perfil guardado que verificar"))
                verificar = self.perfil[:2]
            self.clase_libre = 0
            self.decisor = None
            self.proc.matriz = None
            self.cal.iniciar(orden["protocolo"], t, verificar)
            self._t_cal = -1e9
        elif cmd == "cancelar":
            self.cal.cancelar(t)
            self.clase_libre = 0
            self._difundir(m_resultado(self.cal))
        elif cmd == "simular":
            if self.fuente.nombre != "simulada":
                return self._responder(cola, m_error("la fuente no es simulada"))
            if self.cal.fase not in TERMINALES:
                return self._responder(cola, m_error("no se puede simular durante la calibración"))
            self.clase_libre = orden["clase"]
        elif cmd == "ping":
            self._responder(cola, '{"tipo":"pong"}')
        elif cmd == "osciloscopio":
            if orden["activo"] and cola is not None:
                self.suscritos.add(cola)
            else:
                self.suscritos.discard(cola)
            self._observar()
        elif cmd == "sesion":
            self._orden_sesion(cola, orden)
        elif cmd == "abrir_carpeta":
            codigo = self.bita.codigo or self._ultimo_codigo
            carpeta = None if codigo is None else self.bita.raiz / codigo
            if carpeta is None or not carpeta.exists():
                return self._responder(
                    cola, m_error("todavía no hay datos guardados de este paciente")
                )
            asyncio.get_running_loop().run_in_executor(None, self.abridor, carpeta)
        elif cmd == "evento":
            if self.bita.registro is None:
                return self._responder(cola, m_error("no hay una sesión iniciada"))
            self.bita.evento(orden, self._mdf)

    def _orden_sesion(self, cola: asyncio.Queue | None, orden: dict) -> None:
        b, accion = self.bita, orden["accion"]
        if accion == "iniciar":
            if b.registro is not None:
                b.terminar("nueva_sesion")
            m = self.cal.modelo if self.proc.matriz is not None else None
            self._cargar_perfil(orden["codigo"])
            self._ultimo_codigo = orden["codigo"]
            b.iniciar(
                orden["codigo"],
                orden["minutos_prescritos"],
                fuente=self.fuente.nombre,
                fs=self.cfg.fs,
                version_contrato=2,
                calibrado=self.proc.matriz is not None,
                exactitud=None if m is None else m.exactitud,
            )
            self._estado_previo = None  # anunciar la sesión en el siguiente estado
        elif b.registro is None:
            self._responder(cola, m_error("no hay una sesión iniciada"))
        elif accion == "resumen":
            self._responder(cola, m_sesion(b.codigo, False, b.resumen()))
        else:
            b.terminar("cliente")
            self._estado_previo = None

    def _tras_calibrar(self) -> None:
        """Calibración completa: guarda el perfil (en un hilo). Verificación: solo lo anuncia."""
        codigo = self.bita.codigo
        if self.cal.modo == "verificar":
            self._difundir(m_perfil(codigo, "verificado", self.perfil[2]))
            return
        if self.cal.modelo is None:
            return
        info = {"fecha": f"{date.today():%Y-%m-%d}", "exactitud": self.cal.modelo.exactitud}
        self.perfil = (self.cal.matriz, self.cal.modelo, info)
        self._guardando = asyncio.get_running_loop().run_in_executor(
            None,
            guardar_perfil,
            self.bita.raiz / codigo,
            self.cal.matriz,
            self.cal.modelo,
            self.cfg,
        )
        self._guardando_codigo = codigo

    def _cargar_perfil(self, codigo: str) -> None:
        """Al iniciar la sesión de un paciente: nada de la calibración anterior sobrevive."""
        self.decisor, self.proc.matriz, self.perfil = None, None, None
        if self.cal.fase in TERMINALES:
            self.cal.reiniciar()
            self._t_cal = -1e9  # la interfaz ve de inmediato que no hay calibración
        try:
            p = cargar_perfil(self.bita.raiz / codigo, self.cfg)
        except ValueError as e:
            return self._difundir(m_perfil(codigo, "incompatible", motivo=str(e)))
        if p is None:
            return self._difundir(m_perfil(codigo, "no_existe"))
        self.perfil = p
        self._difundir(m_perfil(codigo, "cargado", p[2]))

    def _observar(self) -> None:
        """Conecta el osciloscopio al procesador solo mientras alguien lo mira."""
        if self.suscritos and self.osc is None:
            self.osc = Osciloscopio(self.cfg.canales, self.cfg.fs)
        self.proc.observador = self.osc.agregar if self.suscritos and self.osc else None

    def _mdf(self, movimiento: str, dur_s: float) -> float | None:
        """MDF del agonista en el último segundo del ejercicio (o menos si fue más corto)."""
        canales = {
            "extension": [0],
            "flexion": [1],
            "pronacion": [2],
            "supinacion": [3],
            "cofre": [2, 3],
        }.get(movimiento)
        n = min(int(min(dur_s, 1.0) * self.cfg.fs), self.buf.capacidad)
        if not canales or n < 1:
            return None
        datos, val = (
            np.empty((n, self.cfg.canales), np.float32),
            np.empty((n, self.cfg.canales), bool),
        )
        if self.buf.ultimas(n, datos, val, np.empty(n, np.int64)) < n or not val[:, canales].all():
            return None
        mdf = [frecuencia_mediana(datos[:, c].astype(np.float64), self.cfg.fs) for c in canales]
        mdf = [v for v in mdf if v is not None]
        return round(float(np.mean(mdf)), 1) if mdf else None

    def _publicar(self, t: float) -> None:
        p, ok = self.proc, self.fresca
        if t - self._t_niv >= self.NIVELES_S:
            self._t_niv = t
            self._difundir(
                m_niveles(
                    int(t * 1000),
                    p.env_uv,
                    p.env_valida & ok,
                    p.activacion,
                    p.activacion_valida & ok,
                )
            )
        # decisiones: solo con señal fresca, decisor entrenado y fuera de la calibración
        if t - self._t_dec >= self.DECISION_S:
            self._t_dec = t
            listo = self.decisor is not None and ok and self.cal.fase in TERMINALES
            d = self.decisor.decision() if listo else None
            if d is not None:
                self._difundir(m_decodificador(int(t * 1000), *d, self.decisor.probabilidades))
            self.bita.tick_decision(self.decisor if listo else None, d is not None)
        # osciloscopio: solo a quien lo pidió, 10 veces por segundo (la interfaz interpola)
        if self.suscritos and self.osc is not None and self.osc.n and t - self._t_osc >= 0.1:
            self._t_osc = t
            msg = m_osc(self.osc.dt_ms, *self.osc.extraer())
            for cola in self.suscritos:
                self._poner(cola, msg)
        estado = (ok, p.matriz is not None, tuple(int(c) for c in p.calidad), self.fuente.error)
        if estado != self._estado_previo or t - self._t_est >= self.ESTADO_S:
            self._t_est, self._estado_previo = t, estado
            self._difundir(self._m_estado())
        activa = self.cal.fase not in TERMINALES
        if (activa and t - self._t_cal >= self.CALIBRACION_S) or self._t_cal < -1e8:
            self._t_cal = t
            self._difundir(m_calibracion(self.cal, t))

    def _m_estado(self) -> str:
        d = self.dec
        return m_estado(
            self.fuente.nombre,
            self.fresca,
            self.proc.matriz is not None,
            self.proc.calidad,
            d.perdidas,
            d.crc_malos + d.cobs_malos + d.formato_malo,
            self.fuente.error,
            self.bita.codigo,
        )

    def _rehacer(self, fs: float) -> None:
        matriz = self.proc.matriz
        self.cfg = dataclasses.replace(self.cfg, fs=fs)
        self.proc = Procesador(self.cfg, matriz)
        self.proc._leidas = self.buf.escritas  # empieza con lo que llegue desde ahora

    # ---- difusión sin bloqueo ----
    @staticmethod
    def _poner(cola: asyncio.Queue, mensaje: str) -> None:
        if cola.full():  # cliente lento: se pierde lo más viejo, nunca se espera
            cola.get_nowait()
        cola.put_nowait(mensaje)

    def _difundir(self, mensaje: str) -> None:
        for cola in self.clientes.values():
            self._poner(cola, mensaje)

    def _responder(self, cola: asyncio.Queue | None, mensaje: str) -> None:
        if cola is not None:
            self._poner(cola, mensaje)

    # ---- red ----
    async def _atender(self, ws: ServerConnection) -> None:
        if not origen_permitido(ws.request.headers.get("Origin")):
            await ws.close(1008, "origen no permitido")
            return
        cola: asyncio.Queue = asyncio.Queue(maxsize=64)
        self.clientes[ws] = cola
        for m in (
            m_hola(self.fuente.nombre, self.cfg.fs, self.cfg.canales),
            self._m_estado(),
            m_calibracion(self.cal, self.reloj()),
        ):
            self._poner(cola, m)
        emisor = asyncio.create_task(self._emitir(ws, cola))
        try:
            async for texto in ws:
                try:
                    self.ordenes.append((cola, leer_orden(texto)))
                except ErrorOrden as e:
                    self._poner(cola, m_error(str(e)))
        except ConnectionClosed:
            pass
        finally:
            emisor.cancel()
            self.clientes.pop(ws, None)
            self.suscritos.discard(cola)
            self._observar()

    @staticmethod
    async def _emitir(ws: ServerConnection, cola: asyncio.Queue) -> None:
        try:
            while True:
                await ws.send(await cola.get())
        except ConnectionClosed:
            pass

    async def _bucle(self) -> None:
        while True:
            await asyncio.sleep(self.PASO_S)
            self.paso(self.reloj())

    async def servir(
        self, host: str = "127.0.0.1", puerto: int = 8765, listo: asyncio.Event | None = None
    ) -> None:
        """Sirve hasta que se cancele la tarea."""
        async with serve(self._atender, host, puerto, max_size=4096) as servidor:
            self.puerto_real = servidor.sockets[0].getsockname()[1]
            if listo is not None:
                listo.set()
            try:
                await asyncio.gather(
                    self.fuente.correr(self.dec.alimentar, self.reloj), self._bucle()
                )
            finally:  # al apagar el motor, la sesión abierta se cierra y se exporta
                self.bita.terminar_ya("cierre_motor")

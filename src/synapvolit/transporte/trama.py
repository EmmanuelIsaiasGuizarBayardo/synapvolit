"""Protocolo de tramas ESP32 → Python, versión 1 (especificación en ``docs/protocolo.md``).

Cada trama viaja codificada con COBS y termina en ``0x00``. Antes de codificar::

    ver(u8) tipo(u8) ...cuerpo... crc16(u16 LE)

* ``tipo = 1`` (EMG): cabecera de 12 bytes, ``n × canales`` muestras ``int16`` intercaladas
  por muestra y, si la bandera lo indica, un bloque IMU de 6 ``int16``.
* ``tipo = 2`` (control): JSON en UTF-8, por ejemplo el saludo ``{"tipo":"hola",...}``.

El CRC es CRC-16/CCITT-FALSE (polinomio 0x1021, valor inicial 0xFFFF) sobre todo lo anterior a
él; ``binascii.crc_hqx`` lo calcula en C.

Memoria: a 2 kHz el trabajo nunca es por muestra en Python, sino por trama (100 por segundo) y
vectorizado. Las tramas se decodifican en búferes fijos y las muestras se copian a un búfer
circular preasignado, así que el flujo continuo no acumula objetos ni crece en memoria.
"""

from __future__ import annotations

import binascii
import json
import struct
from collections import deque

import numpy as np

from .cobs import cobs_codificar, cobs_decodificar, cobs_max

VERSION = 1
TIPO_EMG = 1
TIPO_CONTROL = 2
CABECERA = struct.Struct("<BBHIBBBB")  # ver, tipo, seq, t_us, n, canales, banderas, reservado
MASCARA_CONTACTO = 0x0F  # bits 0-3: contacto perdido en los canales 0-3
BIT_SATURACION = 1 << 4  # alguna muestra de la trama llegó al tope del ADC
BIT_IMU = 1 << 5  # la trama trae un bloque IMU después de las muestras
BYTES_IMU = 12  # 6 × int16: acelerómetro y giroscopio
MAX_CRUDO = 2048  # tamaño máximo de una trama sin codificar
LSB_UV_DEFECTO = 0.5  # µV por cuenta del ADC si el saludo no dice otra cosa


def crc16(buf: bytes | bytearray, n: int) -> int:
    """CRC-16/CCITT-FALSE de ``buf[:n]`` (valor de verificación de "123456789": 0x29B1)."""
    return binascii.crc_hqx(buf[:n], 0xFFFF)


class BufferCircular:
    """Últimas muestras en µV, con validez por canal y tiempo por muestra; todo preasignado.

    La ausencia de datos es explícita (estándar DUNNE, señal externa): una muestra perdida o
    con el electrodo sin contacto queda con ``valido = False``. Su valor numérico no significa
    nada y ningún consumidor debe usarlo.

    Parameters
    ----------
    canales : int
        Canales de sEMG.
    capacidad : int
        Muestras por canal que se conservan (8192 son ~4 s a 2 kHz).
    """

    def __init__(self, canales: int = 4, capacidad: int = 8192) -> None:
        self.canales, self.capacidad = canales, capacidad
        self.datos = np.zeros((capacidad, canales), np.float32)
        self.valido = np.zeros((capacidad, canales), bool)
        self.t_us = np.zeros(capacidad, np.int64)
        self.escritas = 0  # total histórico; la posición de escritura es escritas % capacidad
        self._rampa = np.arange(capacidad, dtype=np.float64)
        self._tmp = np.empty(capacidad, np.float64)
        # tabla de validez por combinación de bits de contacto (sin ramas por canal en cada trama)
        self._validez = np.ones((16, canales), bool)
        for b in range(16):
            for c in range(min(canales, 4)):
                self._validez[b, c] = not (b >> c) & 1

    def _tiempos(self, i: int, n: int, t0_us: float, dt_us: float) -> None:
        np.multiply(self._rampa[:n], dt_us, out=self._tmp[:n])
        np.add(self._tmp[:n], t0_us, out=self._tmp[:n])
        k1 = min(n, self.capacidad - i)
        self.t_us[i : i + k1] = self._tmp[:k1]
        self.t_us[: n - k1] = self._tmp[k1:n]

    def escribir(
        self, cuentas: np.ndarray, lsb_uv: float, contacto: int, t0_us: int, fs: float
    ) -> None:
        """Agrega un bloque ``(n, canales)`` de cuentas ``int16`` como µV."""
        n, i = len(cuentas), self.escritas % self.capacidad
        k1 = min(n, self.capacidad - i)
        np.multiply(cuentas[:k1], lsb_uv, out=self.datos[i : i + k1])
        np.multiply(cuentas[k1:], lsb_uv, out=self.datos[: n - k1])
        fila = self._validez[contacto & MASCARA_CONTACTO]
        self.valido[i : i + k1] = fila
        self.valido[: n - k1] = fila
        self._tiempos(i, n, t0_us, 1e6 / fs)
        self.escritas += n

    def marcar_hueco(self, n: int, t_fin_us: int, fs: float) -> None:
        """Registra ``n`` muestras perdidas que terminan justo antes de ``t_fin_us``."""
        n = min(n, self.capacidad)
        i, dt = self.escritas % self.capacidad, 1e6 / fs
        k1 = min(n, self.capacidad - i)
        self.datos[i : i + k1] = 0.0
        self.datos[: n - k1] = 0.0
        self.valido[i : i + k1] = False
        self.valido[: n - k1] = False
        self._tiempos(i, n, t_fin_us - n * dt, dt)
        self.escritas += n

    def ultimas(self, m: int, datos: np.ndarray, valido: np.ndarray, t_us: np.ndarray) -> int:
        """Copia las ``m`` muestras más recientes, en orden temporal, a arreglos del llamador.

        Returns
        -------
        int
            Muestras copiadas (menos de ``m`` si todavía no hay tantas).
        """
        m = min(m, self.escritas, self.capacidad)
        fin = self.escritas % self.capacidad
        ini = (fin - m) % self.capacidad
        k1 = min(m, self.capacidad - ini)
        for dst, src in ((datos, self.datos), (valido, self.valido), (t_us, self.t_us)):
            dst[:k1] = src[ini : ini + k1]
            dst[k1:m] = src[: m - k1]
        return m


class Empaquetador:
    """Arma tramas como lo hace el firmware, en búferes preasignados (usado por el simulador)."""

    def __init__(self, canales: int = 4, por_trama: int = 20) -> None:
        self.canales, self.por_trama = canales, por_trama
        self.largo_emg = CABECERA.size + 2 * canales * por_trama + 2
        self._crudo = bytearray(MAX_CRUDO)
        self._muestras = np.frombuffer(
            self._crudo, "<i2", canales * por_trama, CABECERA.size
        ).reshape(por_trama, canales)
        self._salida = bytearray(cobs_max(MAX_CRUDO) + 1)
        self._vista = memoryview(self._salida)

    def _cerrar(self, largo: int) -> memoryview:
        crc = crc16(self._crudo, largo - 2)
        self._crudo[largo - 2] = crc & 0xFF
        self._crudo[largo - 1] = crc >> 8
        m = cobs_codificar(self._crudo, largo, self._salida)
        self._salida[m] = 0
        return self._vista[: m + 1]

    def emg(self, seq: int, t_us: int, bloque: np.ndarray, banderas: int = 0) -> memoryview:
        """Trama EMG codificada, lista para el puerto (válida hasta la siguiente llamada)."""
        CABECERA.pack_into(
            self._crudo,
            0,
            VERSION,
            TIPO_EMG,
            seq & 0xFFFF,
            t_us & 0xFFFFFFFF,
            self.por_trama,
            self.canales,
            banderas & ~BIT_IMU,
            0,
        )
        self._muestras[...] = bloque
        return self._cerrar(self.largo_emg)

    def control(self, mensaje: dict) -> memoryview:
        """Trama de control con un mensaje JSON."""
        cuerpo = json.dumps(mensaje, separators=(",", ":")).encode()
        largo = 2 + len(cuerpo) + 2
        if largo > MAX_CRUDO:
            raise ValueError("mensaje de control demasiado largo")
        self._crudo[0], self._crudo[1] = VERSION, TIPO_CONTROL
        self._crudo[2 : 2 + len(cuerpo)] = cuerpo
        return self._cerrar(largo)


class Decodificador:
    """Intérprete puro del protocolo: recibe bytes y deja muestras en un ``BufferCircular``.

    No abre puertos, no usa hilos ni lee el reloj (estándar DUNNE, señal externa), así que se
    prueba con tramas sintéticas. Acepta los bytes en pedazos de cualquier tamaño.

    Detecta y cuenta: CRC malo, COBS inválido, versión o formato desconocido, tramas perdidas
    (por número de secuencia), saturación y reinicios del microcontrolador. Las tramas perdidas
    se escriben como hueco explícito para que el tiempo siga siendo continuo.
    """

    def __init__(
        self, buffer: BufferCircular, fs: float = 2000.0, lsb_uv: float = LSB_UV_DEFECTO
    ) -> None:
        self.buf, self.fs, self.lsb_uv = buffer, fs, lsb_uv
        self._acc = bytearray(2 * cobs_max(MAX_CRUDO))
        self._n = 0
        self._crudo = bytearray(MAX_CRUDO)
        self.control: deque[dict] = deque(maxlen=64)  # mensajes de control, ya interpretados
        self.tramas = self.crc_malos = self.cobs_malos = self.formato_malo = 0
        self.perdidas = self.saturadas = self.reinicios = self.desbordes = 0
        self._seq_esp = -1
        self._t_prev = -1
        self._vueltas = 0

    def alimentar(self, datos: bytes | bytearray | memoryview) -> int:
        """Procesa bytes recibidos y devuelve cuántas tramas EMG nuevas quedaron en el búfer."""
        nuevas, pos, m, cap = 0, 0, len(datos), len(self._acc)
        while pos < m:
            k = min(cap - self._n, m - pos)
            self._acc[self._n : self._n + k] = datos[pos : pos + k]
            self._n += k
            pos += k
            nuevas += self._procesar()
            if self._n == cap:  # un búfer entero sin delimitador es basura: se descarta
                self.desbordes += 1
                self._n = 0
        return nuevas

    def _procesar(self) -> int:
        nuevas = ini = 0
        while (fin := self._acc.find(0, ini, self._n)) >= 0:
            if fin > ini:
                largo = cobs_decodificar(self._acc, ini, fin, self._crudo)
                if largo < 0:
                    self.cobs_malos += 1
                else:
                    nuevas += self._trama(largo)
            ini = fin + 1
        if ini:  # lo que queda es una trama incompleta: se mueve al inicio
            resto = self._n - ini
            self._acc[:resto] = self._acc[ini : self._n]
            self._n = resto
        return nuevas

    def _trama(self, largo: int) -> int:
        c = self._crudo
        if largo < 4 or crc16(c, largo - 2) != c[largo - 2] | (c[largo - 1] << 8):
            self.crc_malos += 1
            return 0
        if c[0] != VERSION:
            self.formato_malo += 1
            return 0
        if c[1] == TIPO_CONTROL:
            self._mensaje(largo)
            return 0
        if c[1] != TIPO_EMG or largo < CABECERA.size + 2:
            self.formato_malo += 1
            return 0
        _, _, seq, t, n, nc, banderas, _ = CABECERA.unpack_from(c, 0)
        esperado = CABECERA.size + 2 * n * nc + (BYTES_IMU if banderas & BIT_IMU else 0) + 2
        if nc != self.buf.canales or largo != esperado:
            self.formato_malo += 1
            return 0
        # reloj del ESP32: uint32 en µs que da la vuelta cada ~71.6 min
        if 0 <= t < self._t_prev:
            if self._t_prev - t > 0x80000000:
                self._vueltas += 1
            else:  # el tiempo retrocedió sin dar la vuelta: el microcontrolador se reinició
                self.reinicios += 1
                self._seq_esp = -1
        self._t_prev = t
        t_abs = t + (self._vueltas << 32)
        if self._seq_esp >= 0 and seq != self._seq_esp:
            hueco = (seq - self._seq_esp) & 0xFFFF
            self.perdidas += hueco
            self.buf.marcar_hueco(hueco * n, t_abs, self.fs)
        self._seq_esp = (seq + 1) & 0xFFFF
        if banderas & BIT_SATURACION:
            self.saturadas += 1
        cuentas = np.frombuffer(c, "<i2", n * nc, CABECERA.size).reshape(n, nc)
        self.buf.escribir(cuentas, self.lsb_uv, banderas, t_abs, self.fs)
        self.tramas += 1
        return 1

    def _mensaje(self, largo: int) -> None:
        try:
            msg = json.loads(self._crudo[2 : largo - 2])
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.formato_malo += 1
            return
        if (
            isinstance(msg, dict) and msg.get("tipo") == "hola"
        ):  # el saludo fija la escala y el muestreo
            self.fs = float(msg.get("fs", self.fs))
            self.lsb_uv = float(msg.get("lsb_uv", self.lsb_uv))
        self.control.append(msg)

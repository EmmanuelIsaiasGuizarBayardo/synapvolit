"""Transporte ESP32 → Python: tramas binarias (COBS + CRC16) y mensajes JSON de control."""

from .cobs import cobs_codificar, cobs_decodificar, cobs_max
from .simulador import ESCENARIOS, Escenario, SimuladorESP32, correr
from .trama import BufferCircular, Decodificador, Empaquetador, crc16

__all__ = [
    "ESCENARIOS",
    "BufferCircular",
    "Decodificador",
    "Empaquetador",
    "Escenario",
    "SimuladorESP32",
    "cobs_codificar",
    "cobs_decodificar",
    "cobs_max",
    "correr",
    "crc16",
]

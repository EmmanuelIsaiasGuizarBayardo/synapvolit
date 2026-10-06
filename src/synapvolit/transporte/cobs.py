"""COBS (Cheshire y Baker, 1999) sobre búferes preasignados.

COBS elimina los ceros de una trama para que el byte ``0x00`` funcione como delimitador
inequívoco en el puerto serie: si se pierde un byte, el receptor se resincroniza en el
siguiente cero. Las dos funciones escriben en un ``bytearray`` que reciben y devuelven la
longitud escrita, en lugar de crear ``bytes`` nuevos en cada trama.
"""

from __future__ import annotations

BLOQUE = 254  # bytes sin cero que caben en un bloque de COBS


def cobs_max(n: int) -> int:
    """Longitud máxima de la codificación de ``n`` bytes (sin el delimitador)."""
    return n + n // BLOQUE + 1


def cobs_codificar(src: bytes | bytearray, n: int, dst: bytearray) -> int:
    """Codifica ``src[:n]`` en ``dst`` y devuelve la longitud, sin el ``0x00`` final.

    Parameters
    ----------
    src : bytes or bytearray
        Datos de entrada; pueden contener ceros.
    n : int
        Cuántos bytes de ``src`` se codifican.
    dst : bytearray
        Destino con al menos ``cobs_max(n)`` bytes.

    Returns
    -------
    int
        Bytes escritos en ``dst``. La forma es la canónica: un bloque final de 254 bytes
        no lleva código ``0x01`` adicional, igual que la implementación de referencia.
    """
    o = i = 0
    while True:
        j = src.find(0, i, n)
        fin = j < 0
        if fin:
            j = n
        lleno = False
        while j - i >= BLOQUE:  # bloque completo: código 0xFF y sin cero implícito
            dst[o] = 0xFF
            dst[o + 1 : o + 1 + BLOQUE] = src[i : i + BLOQUE]
            o += BLOQUE + 1
            i += BLOQUE
            lleno = True
        k = j - i
        if not (fin and k == 0 and lleno):
            dst[o] = k + 1
            dst[o + 1 : o + 1 + k] = src[i:j]
            o += k + 1
        if fin:
            return o
        i = j + 1


def cobs_decodificar(src: bytes | bytearray, i0: int, i1: int, dst: bytearray) -> int:
    """Decodifica ``src[i0:i1]`` (sin el delimitador) en ``dst``.

    Returns
    -------
    int
        Bytes decodificados, o ``-1`` si la trama no es COBS válido (un cero interno o un
        código que apunta fuera de la trama), que es como se manifiesta un byte corrupto.
    """
    o, i, cap = 0, i0, len(dst)
    while i < i1:
        c = src[i]
        if c == 0:
            return -1
        k = c - 1
        i += 1
        if i + k > i1 or o + k + 1 > cap:
            return -1
        dst[o : o + k] = src[i : i + k]
        o += k
        i += k
        if c != 0xFF and i < i1:  # cero implícito, salvo al final de la trama
            dst[o] = 0
            o += 1
    return o

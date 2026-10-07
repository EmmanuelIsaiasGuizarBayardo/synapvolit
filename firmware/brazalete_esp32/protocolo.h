// Protocolo de tramas v1 (docs/protocolo.md): CRC-16/CCITT-FALSE, COBS y armado de tramas.
// Sin dependencias de Arduino: se compila igual en el ESP32 y en la PC, y así se prueba en la PC
// contra la implementación de Python (tests/test_firmware_protocolo.py exige bytes idénticos).
#pragma once
#include <stddef.h>
#include <stdint.h>

namespace proto {

constexpr uint8_t VERSION = 1;
constexpr uint8_t TIPO_EMG = 1;
constexpr uint8_t TIPO_CONTROL = 2;
constexpr uint8_t BIT_SATURACION = 1 << 4;
constexpr size_t CABECERA = 12;

// CRC-16/CCITT-FALSE (polinomio 0x1021, inicial 0xFFFF). Verificación: "123456789" -> 0x29B1.
inline uint16_t crc16(const uint8_t* d, size_t n) {
  uint16_t c = 0xFFFF;
  for (size_t i = 0; i < n; i++) {
    c ^= static_cast<uint16_t>(d[i]) << 8;
    for (int b = 0; b < 8; b++) c = (c & 0x8000) ? static_cast<uint16_t>((c << 1) ^ 0x1021) : static_cast<uint16_t>(c << 1);
  }
  return c;
}

// COBS canónico (igual que synapvolit.transporte.cobs): un bloque final de 254 bytes no lleva 0x01
// extra. dst necesita n + n/254 + 1 bytes. Devuelve la longitud, sin el 0x00 delimitador.
inline size_t cobs(const uint8_t* src, size_t n, uint8_t* dst) {
  size_t o = 0, i = 0;
  while (true) {
    size_t j = i;
    while (j < n && src[j] != 0) j++;
    const bool fin = (j == n);
    bool lleno = false;
    while (j - i >= 254) {
      dst[o++] = 0xFF;
      for (size_t k = 0; k < 254; k++) dst[o++] = src[i++];
      lleno = true;
    }
    const size_t k = j - i;
    if (!(fin && k == 0 && lleno)) {
      dst[o++] = static_cast<uint8_t>(k + 1);
      while (i < j) dst[o++] = src[i++];
    }
    if (fin) return o;
    i = j + 1;
  }
}

inline void pon16(uint8_t* p, uint16_t v) { p[0] = v & 0xFF; p[1] = v >> 8; }

// Trama EMG sin codificar: cabecera de 12 bytes, muestras int16 intercaladas y CRC. Devuelve la longitud.
inline size_t armar_emg(uint8_t* crudo, uint16_t seq, uint32_t t_us, uint8_t n, uint8_t nc, uint8_t banderas,
                        const int16_t* muestras) {
  crudo[0] = VERSION;
  crudo[1] = TIPO_EMG;
  pon16(crudo + 2, seq);
  pon16(crudo + 4, static_cast<uint16_t>(t_us & 0xFFFF));
  pon16(crudo + 6, static_cast<uint16_t>(t_us >> 16));
  crudo[8] = n;
  crudo[9] = nc;
  crudo[10] = banderas;
  crudo[11] = 0;
  size_t p = CABECERA;
  for (size_t i = 0; i < static_cast<size_t>(n) * nc; i++, p += 2) pon16(crudo + p, static_cast<uint16_t>(muestras[i]));
  pon16(crudo + p, crc16(crudo, p));
  return p + 2;
}

// Trama de control: JSON en UTF-8 (el saludo "hola"). Devuelve la longitud.
inline size_t armar_control(uint8_t* crudo, const char* json, size_t len) {
  crudo[0] = VERSION;
  crudo[1] = TIPO_CONTROL;
  for (size_t i = 0; i < len; i++) crudo[2 + i] = static_cast<uint8_t>(json[i]);
  pon16(crudo + 2 + len, crc16(crudo, 2 + len));
  return len + 4;
}

}  // namespace proto

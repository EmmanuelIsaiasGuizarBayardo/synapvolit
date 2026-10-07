// Prueba en la PC: genera tramas con protocolo.h y las escribe en binario por stdout.
// La prueba de Python exige que sean idénticas, byte a byte, a las de synapvolit.transporte.
#include <cstdio>
#include <cstring>
#include "protocolo.h"

int main() {
  uint8_t crudo[1024], cod[1100];
  int16_t m[20 * 4];
  for (uint16_t s = 0; s < 300; s++) {
    for (int i = 0; i < 80; i++) m[i] = static_cast<int16_t>((s * 977 + i * 131) % 65536 - 32768);  // incluye ceros y 0xFF
    if (s % 7 == 0) m[5] = 0;
    const uint8_t ban = (s % 11 == 0) ? proto::BIT_SATURACION : 0;
    size_t n = proto::armar_emg(crudo, s, 4294900000u + s * 10000u, 20, 4, ban, m);  // cruza la vuelta del reloj
    size_t c = proto::cobs(crudo, n, cod);
    cod[c] = 0;
    fwrite(cod, 1, c + 1, stdout);
    if (s == 150) {
      const char* j = "{\"tipo\":\"hola\",\"fs\":2000,\"lsb_uv\":0.75}";
      n = proto::armar_control(crudo, j, strlen(j));
      c = proto::cobs(crudo, n, cod);
      cod[c] = 0;
      fwrite(cod, 1, c + 1, stdout);
    }
  }
  return 0;
}

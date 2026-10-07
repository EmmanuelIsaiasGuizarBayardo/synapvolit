// Brazalete WristQuest: 4 canales de sEMG (front-end analógico -> ADC del ESP32) con el protocolo v1.
//
// Por qué C++ y no MicroPython: el muestreo a 2 kHz necesita un periodo estable de 500 µs. En
// MicroPython el recolector de basura y el intérprete meten pausas de milisegundos; aquí un
// temporizador de alta resolución (esp_timer) dispara la lectura y un anillo de tramas desacopla el
// muestreo del envío por USB, así que una escritura lenta no mueve el reloj de muestreo.
//
// Arduino IDE: placa "ESP32 Dev Module" (núcleo de Espressif 2.x o 3.x). Monitor serie CERRADO:
// el puerto lo usa el motor (uv run python -m synapvolit.servidor --fuente serie --puerto-serie COMx).
#include <Arduino.h>

#include "esp_timer.h"
#include "protocolo.h"

// ---------------- Configuración: ajustar al hardware ----------------
constexpr uint32_t FS = 2000;            // muestras por segundo y canal
constexpr uint8_t CANALES = 4;           // orden: extensión, flexión, pronación, supinación
constexpr uint8_t POR_TRAMA = 20;        // 10 ms por trama a 2 kHz
constexpr uint8_t PINES[CANALES] = {36, 39, 34, 35};  // ADC1 del ESP32 clásico (ADC2 choca con el WiFi)
constexpr float RANGO_ADC_MV = 3100.0f;  // atenuación de 11 dB: ~0 a 3.1 V a escala completa
constexpr float GANANCIA_FRONTEND = 1000.0f;  // ganancia total del front-end analógico (ver su hoja de datos)
constexpr uint32_t BAUDIOS = 921600;     // ignorado si la placa usa USB nativo (ESP32-S3)
constexpr uint32_t HOLA_CADA_MS = 2000;
constexpr uint32_t CALIBRA_OFFSET_MS = 1000;  // al arrancar: media de cada canal = nivel de reposo del front-end
// µV en la piel por cuenta del ADC: (mV por cuenta) / ganancia × 1000
const float LSB_UV = RANGO_ADC_MV / 4095.0f / GANANCIA_FRONTEND * 1000.0f;

// Si el front-end detecta electrodos sueltos (lead-off), devolver aquí un bit por canal (0-3).
static inline uint8_t contacto_perdido() { return 0; }

// ---------------- Muestreo (tarea del temporizador) ----------------
struct Trama {
  uint16_t seq;
  uint32_t t_us;
  uint8_t banderas;
  int16_t m[POR_TRAMA * CANALES];
};
constexpr uint8_t ANILLO = 16;  // 160 ms de holgura si el USB se atrasa
static Trama anillo[ANILLO];
static volatile uint8_t escribe = 0, lee = 0;  // un productor (temporizador) y un consumidor (loop)
static volatile uint32_t descartadas = 0;      // tramas que no cupieron: Python las ve como hueco de seq
static volatile uint32_t carga_max_us = 0;     // peor duración de una lectura: diagnóstico del timing
static uint16_t seq = 0;
static uint8_t k = 0;
static int32_t medio[CANALES];
static int64_t suma[CANALES];
static uint32_t n_calibra = 0;
static volatile bool listo = false;

static void muestrear(void*) {
  const int64_t t0 = esp_timer_get_time();
  if (!listo) {  // primero, el nivel de reposo de cada canal (el front-end centra la señal en ~VCC/2)
    for (uint8_t c = 0; c < CANALES; c++) suma[c] += analogRead(PINES[c]);
    if (++n_calibra >= FS * CALIBRA_OFFSET_MS / 1000) {
      for (uint8_t c = 0; c < CANALES; c++) medio[c] = static_cast<int32_t>(suma[c] / n_calibra);
      listo = true;
    }
    return;
  }
  Trama& t = anillo[escribe];
  if (k == 0) {
    t.seq = seq;
    t.t_us = static_cast<uint32_t>(t0);  // el reloj de 32 bits da la vuelta cada ~71.6 min: Python lo desenvuelve
    t.banderas = contacto_perdido();
  }
  for (uint8_t c = 0; c < CANALES; c++) {
    const int v = analogRead(PINES[c]);
    if (v <= 2 || v >= 4093) t.banderas |= proto::BIT_SATURACION;
    t.m[k * CANALES + c] = static_cast<int16_t>(v - medio[c]);
  }
  if (++k == POR_TRAMA) {
    k = 0;
    seq++;
    const uint8_t sig = (escribe + 1) % ANILLO;
    __sync_synchronize();  // la trama queda completa en memoria antes de publicarla al otro núcleo
    if (sig == lee) descartadas = descartadas + 1;  // anillo lleno: esta trama se reescribe
    else escribe = sig;
  }
  const uint32_t dur = static_cast<uint32_t>(esp_timer_get_time() - t0);
  if (dur > carga_max_us) carga_max_us = dur;
}

// ---------------- Envío (loop) ----------------
static uint8_t crudo[proto::CABECERA + 2 * POR_TRAMA * CANALES + 2 + 512];
static uint8_t codificado[sizeof(crudo) + sizeof(crudo) / 254 + 2];

static void enviar(size_t largo) {
  const size_t m = proto::cobs(crudo, largo, codificado);
  codificado[m] = 0;  // delimitador
  Serial.write(codificado, m + 1);
}

static void enviar_hola() {
  char json[256];
  const int len = snprintf(json, sizeof(json),
                           "{\"tipo\":\"hola\",\"version\":1,\"fs\":%lu,\"canales\":%u,\"por_trama\":%u,"
                           "\"lsb_uv\":%.5f,\"fuente\":\"brazalete\",\"firmware\":\"1.0.0\",\"adc\":\"esp32-interno\","
                           "\"descartadas\":%lu,\"carga_max_us\":%lu}",
                           static_cast<unsigned long>(FS), CANALES, POR_TRAMA, LSB_UV,
                           static_cast<unsigned long>(descartadas), static_cast<unsigned long>(carga_max_us));
  enviar(proto::armar_control(crudo, json, static_cast<size_t>(len)));
}

void setup() {
  Serial.setTxBufferSize(4096);
  Serial.begin(BAUDIOS);
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  esp_timer_create_args_t args = {};
  args.callback = &muestrear;
  args.dispatch_method = ESP_TIMER_TASK;  // contexto de tarea: analogRead no se puede llamar desde una ISR
  args.name = "emg";
  esp_timer_handle_t temporizador;
  esp_timer_create(&args, &temporizador);
  esp_timer_start_periodic(temporizador, 1000000UL / FS);
}

void loop() {
  static uint32_t ultimo_hola = 0;
  if (!listo) { delay(10); return; }
  while (lee != escribe) {
    __sync_synchronize();
    const Trama& t = anillo[lee];
    enviar(proto::armar_emg(crudo, t.seq, t.t_us, POR_TRAMA, CANALES, t.banderas, t.m));
    lee = (lee + 1) % ANILLO;
  }
  if (millis() - ultimo_hola >= HOLA_CADA_MS) {
    ultimo_hola = millis();
    enviar_hola();
  }
  delay(1);  // cede la CPU; a 100 tramas/s hay de sobra
}

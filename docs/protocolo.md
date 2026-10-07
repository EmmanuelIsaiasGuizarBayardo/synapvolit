# Protocolo ESP32 → Python, versión 1

Un solo enlace serie lleva dos tipos de trama. Cada trama se codifica con COBS y termina en
`0x00`; si se pierde un byte, el receptor se resincroniza en el siguiente cero. Todos los
enteros van en little-endian.

## Trama sin codificar

| Campo | Tipo | Contenido |
|---|---|---|
| `ver` | u8 | Versión del protocolo: 1 |
| `tipo` | u8 | 1 = EMG, 2 = control (JSON) |
| cuerpo | | Según el tipo (abajo) |
| `crc` | u16 | CRC-16/CCITT-FALSE (polinomio 0x1021, inicial 0xFFFF) de todo lo anterior |

Valor de verificación del CRC: `"123456789"` → `0x29B1`.

### Cuerpo EMG (tipo 1)

| Campo | Tipo | Contenido |
|---|---|---|
| `seq` | u16 | Número de trama; da la vuelta en 65535. Un salto = tramas perdidas |
| `t_us` | u32 | Reloj del microcontrolador al tomar la primera muestra; da la vuelta cada ~71.6 min |
| `n` | u8 | Muestras por canal (20 a 2 kHz = 10 ms) |
| `canales` | u8 | 4 |
| `banderas` | u8 | Bits 0-3: contacto perdido en el canal 0-3; bit 4: saturación; bit 5: hay bloque IMU |
| reservado | u8 | 0 |
| muestras | int16 × n × canales | Intercaladas por muestra: s0c0 s0c1 s0c2 s0c3 s1c0 ... |
| IMU (opcional) | int16 × 6 | Acelerómetro y giroscopio, si el bit 5 está activo |

Con 4 canales y 20 muestras, la trama mide 174 bytes antes de COBS y ~176 en el cable: 17.6 KB/s
a 2 kHz, holgado a 460800 baudios.

### Cuerpo de control (tipo 2)

JSON en UTF-8. El microcontrolador envía el saludo al conectar y cada 2 s, para que un receptor
que llega tarde conozca el muestreo y la escala:

```json
{"tipo":"hola","version":1,"fs":2000,"canales":4,"por_trama":20,"lsb_uv":0.5,"fuente":"simulada"}
```

`lsb_uv` convierte cuentas del ADC a µV. `fuente` vale `"simulada"` o `"brazalete"`: la interfaz
nunca presenta lo simulado como real.

## Comportamiento del receptor

| Situación | Qué hace `Decodificador` |
|---|---|
| CRC o COBS inválido | Descarta la trama y lo cuenta (`crc_malos`, `cobs_malos`) |
| Salto de `seq` | Cuenta `perdidas` y escribe el hueco como muestras inválidas, para que el tiempo siga continuo |
| Bit de contacto | Marca inválidas las muestras de ese canal, no las de los demás |
| `t_us` da la vuelta | Lo desenvuelve a 64 bits |
| `t_us` retrocede sin dar la vuelta | Lo trata como reinicio del microcontrolador (`reinicios`) |

La ausencia es siempre explícita: `BufferCircular.valido` dice qué muestras existen. Su valor
numérico en una muestra inválida no significa nada.

## Validación

COBS se prueba con los vectores canónicos y contra la biblioteca independiente `cobs`; el CRC,
contra su valor de verificación (`tests/test_transporte_*.py`).

## Implementación del lado del microcontrolador

`firmware/brazalete_esp32/` contiene el firmware de referencia para ESP32 (Arduino, C++). Su
`protocolo.h` produce bytes idénticos a `Empaquetador`, verificado en `tests/test_firmware_protocolo.py`.

El motor acepta además la orden `{"cmd":"apagar"}` por WebSocket, solo de programas locales (sin
encabezado `Origin`): la usa el lanzador de WristQuest para cerrar en orden y exportar la sesión.

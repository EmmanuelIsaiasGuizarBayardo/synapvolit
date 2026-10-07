# Firmware del brazalete (ESP32, protocolo v1)

Lee 4 canales del front-end analógico con el ADC del ESP32 a 2 kHz y los envía al motor con el
protocolo v1 (`docs/protocolo.md`): tramas de 10 ms con COBS, CRC16 y un saludo JSON cada 2 s.
`protocolo.h` se prueba en la PC contra el motor (`tests/test_firmware_protocolo.py`): los bytes son
idénticos a los de `synapvolit.transporte`.

## Seguridad eléctrica: antes de conectar a una persona

El brazalete queda unido por USB a la computadora. Con electrodos sobre la piel, una laptop
conectada a la red eléctrica puede dejar pasar corriente de fuga hacia la persona. Para cualquier
prueba con personas (y con niños más aún): laptop **desconectada del cargador**, o un aislador
galvánico USB entre la computadora y el ESP32, y un front-end diseñado para biopotenciales.

## Configuración (al inicio de `brazalete_esp32.ino`)

| Constante | Qué es |
|---|---|
| `PINES` | Pines ADC1 de los canales, en orden extensión, flexión, pronación, supinación. ESP32 clásico: 36, 39, 34, 35. ESP32-S3: GPIO 1 a 10 |
| `GANANCIA_FRONTEND` | Ganancia total del front-end; define `lsb_uv`, la escala en µV que usa el motor |
| `RANGO_ADC_MV` | Escala completa del ADC con atenuación de 11 dB (~3100 mV) |
| `FS`, `POR_TRAMA` | 2000 Hz y 20 muestras: tramas de 10 ms |
| `contacto_perdido()` | Si el front-end detecta electrodos sueltos, devolver un bit por canal |

Al arrancar, el firmware mide 1 s el nivel de reposo de cada canal (el front-end centra la señal en
~VCC/2) y lo resta; el motor quita el resto con su pasa-banda. No hace filtrado: todo el procesamiento
vive en el motor.

## Cargar y probar

1. Arduino IDE con el núcleo ESP32 de Espressif (2.x o 3.x), placa "ESP32 Dev Module".
2. Abrir `brazalete_esp32.ino` (con `protocolo.h` en la misma carpeta) y cargar.
3. **Cerrar el monitor serie**: el puerto lo usa el motor.
4. `uv run python -m synapvolit.servidor --fuente serie --puerto-serie COM3` (o con el lanzador).
5. En el juego, Configuración → Monitor de señal: deben verse los cuatro canales.

## Diagnóstico de timing

El saludo incluye `carga_max_us` (la lectura más lenta de los 4 canales) y `descartadas` (tramas que
no cupieron en el anillo porque el USB se atrasó). Con `analogRead` cada lectura tarda decenas de µs:
a 2 kHz sobra tiempo (periodo de 500 µs), pero si `carga_max_us` se acerca al periodo, el muestreo
deja de ser regular. Para subir de frecuencia o reducir la fluctuación, el siguiente paso es el modo
continuo del ADC con DMA o un ADC externo (por ejemplo un ADS1299, que además detecta electrodos
sueltos).

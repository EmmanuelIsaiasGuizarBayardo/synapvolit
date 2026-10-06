# Procesamiento en tiempo real

```
BufferCircular → validez efectiva → pasa-banda → muesca → envolvente RMS → normalización
                                        └────────→ calidad de contacto ──┘
```

Todo se calcula por bloques (una trama = 10 ms), con estado entre bloques y búferes reservados una
sola vez. Ningún valor asume 2 kHz: todo se deriva de `fs`, que llega en el saludo del brazalete.

| Etapa | Valor por defecto | Por qué |
|---|---|---|
| Pasa-banda | Butterworth 20-450 Hz, 4 polos por flanco | Banda útil de la sEMG de superficie; quita movimiento y deriva |
| Muesca | 60 Hz, Q = 10 | Q alta (30) timbra ~160 ms tras una ráfaga de red; Q = 10, ~53 ms |
| Envolvente | RMS exacta en ventana de 150 ms | GDD: 100-200 ms. Retardo medio ~75 ms |
| Asentamiento | 50 ms tras cada hueco | Los filtros tardan en olvidar el escalón del hueco |
| Envolvente válida | ≥ 80% de muestras válidas en la ventana | Ausencia explícita, nunca un cero |

## Estados de contacto

Se evalúan cada 10 ms sobre la mediana de los últimos 250 ms, con histéresis: empeorar exige
250 ms y mejorar 500 ms. Los umbrales son un punto de partida y deben ajustarse con el brazalete.

| Estado | Condición |
|---|---|
| Sin evaluar | Primeros 250 ms |
| Malo | Bandera de sin contacto o hueco; RMS en banda < 0.5 µV (plano); > 1% de muestras en el tope del ADC; red > 100 µV RMS |
| Dudoso | Red > 20 µV RMS |
| Bueno | Ninguna de las anteriores |

La red se mide como el exceso de amplitud a 60 Hz sobre 52 y 68 Hz, con demoduladores coherentes
de ~1 Hz de ancho de banda. Así una contracción fuerte, que es de banda ancha, no se confunde con
un electrodo mal pegado.

Nada que dependa de la señal se usa con contacto malo: `activacion_valida` exige envolvente
válida y contacto distinto de malo.

## Normalización

`a = (envolvente − reposo) / (referencia − reposo)`, recortada a [0, 1.5]. La referencia de cada
canal es la mediana entre repeticiones del percentil 95 de su envolvente en su propio movimiento.
La co-contracción es la razón antagonista / agonista (extensión ↔ flexión, pronación ↔ supinación).
La matriz vive en memoria.

## Costo medido

~0.26 ms por bloque de 10 ms a 2 kHz y ~0.29 ms a 3 kHz: menos del 3% de un núcleo.

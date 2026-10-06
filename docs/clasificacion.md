# Clasificación e intensidad

## Rasgos

Por canal, en la misma ventana de 150 ms de la envolvente: `log1p(RMS)` y `log1p(DASDV)`, donde
DASDV es la RMS de la primera diferencia. La RMS mide amplitud y la DASDV además refleja el
contenido de frecuencia. Con 4 canales son 8 rasgos. Los calcula el mismo `Procesador` del tiempo
real, así que calibración y uso comparten exactamente la misma cadena.

## Modelo

LDA con encogimiento de Ledoit-Wolf (`solver="lsqr", shrinkage="auto"`), entrenado al terminar la
calibración guiada con:

* reposo inicial y descansos entre repeticiones (como reposo);
* cada contracción, sin sus primeros 0.5 s (a lo más el 30% de la repetición).

La exactitud se estima con validación cruzada agrupada por repetición (`StratifiedGroupKFold`):
ninguna ventana de una repetición se usa a la vez para entrenar y evaluar. Con una sola repetición
no hay estimación honesta y se reporta como no disponible.

El entrenamiento con su validación cruzada tarda ~0.1 s y corre en un hilo aparte
(`run_in_executor`): mientras tanto el bucle sigue procesando y publicando niveles.

En línea no se llama a scikit-learn: la decisión es `W·x + b` y un softmax sobre arreglos
reservados. Una prueba verifica que coincide con `predict_proba`.

## Decisión

Las probabilidades de los últimos 12 pasos (~120 ms) se promedian con una suma corriente. La clase
es la de mayor probabilidad media y la confianza, esa probabilidad. Si menos del 75% de los pasos
de la ventana tienen rasgos válidos, no hay decisión. Se publica a 8 Hz.

## Intensidad y co-contracción

Con `p_m = referencia_m − reposo` (el patrón de cuatro canales del movimiento `m`):

* **Intensidad**: `I = (e − r)·p_m / (p_m·p_m)`, el factor que mejor explica la envolvente actual
  como una fracción del patrón de calibración. Vale 0 en reposo y 1 a la fuerza de la calibración.
* **Co-contracción**: se ajusta `e − r ≈ a·p_m + c·p_antagonista` con ambos patrones a la vez y se
  reporta `c / a`. Ajustarlos juntos evita contar como antagonista la parte compartida de los
  patrones (diafonía). Si los patrones son casi paralelos (número de condición > 30), no se reporta.

## Evaluación con datos reales

```powershell
uv run python -m synapvolit.clasificacion
```

Entrena con los ensayos 1-3 y evalúa los ensayos 4-7 por la ruta en línea completa, con
decisiones a 8 Hz: exactitud, matriz de confusión, sensibilidad por clase, intensidad media y
latencia hasta la primera decisión correcta.

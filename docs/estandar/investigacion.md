<!-- Archivo del estandar DUNNE, generado por la plantilla. No se edita aqui:
     se actualiza con 'uvx copier update --trust'. -->

# Módulo: investigación

Aplica porque el proyecto se declaró de investigación.

## Datos

- **REGLA DURA.** `data/raw/` es inmutable: ningún script escribe ahí. Todo derivado va a `data/processed/`.
- **PREFERENCIA fuerte.** `data/raw/` sigue BIDS-EEG (Pernet et al., 2019) y se lee y escribe con `mne-bids`. Un dataset ajeno se convierte al ingresar; el código no se adapta a su formato.
- La procedencia de cada dataset (origen, fecha, licencia) se registra en `data/raw/README.md`.

## Libretas

- **REGLA DURA.** `notebooks/` no contiene lógica reutilizable. Toda función que se use más de una vez vive en `src/synapvolit/`; las libretas solo orquestan y visualizan.

## Reproducibilidad

**REGLA DURA.** Todo resultado reportado debe poder reconstruirse:

1. `set_seed(seed)` al inicio del script, antes de inicializar CUDA.
2. El `RunContext` (semilla, SHA del commit y estado del árbol) se guarda junto a las métricas, en el mismo archivo.
3. Si `git_dirty` es verdadero, el resultado no es reproducible desde el SHA, y se advierte.

```python
from synapvolit.reproducibility import get_run_context, set_seed

set_seed(42)
ctx = get_run_context(seed=42)
metricas["run_context"] = ctx.as_dict()
```

El determinismo cuesta rendimiento: se activa por defecto y solo se relaja en entrenamientos largos donde baste la reproducibilidad aproximada.

## Fuga de datos

### Reglas duras

- Validación cruzada **por sujeto o por bloques**. Nunca se mezclan épocas de un mismo sujeto entre entrenamiento y prueba.
- Todo lo que se ajusta con datos (escaladores, CSP, selección de *features*, reducción de dimensión) se ajusta **solo** con entrenamiento. En la práctica, un `sklearn.pipeline.Pipeline` completo se pasa al validador cruzado; nunca datos ya transformados.

### Modos de fuga propios del EEG

1. **Autocorrelación temporal.** Épocas adyacentes son casi duplicados, así que una partición aleatoria dentro de un sujeto filtra información. Se parte por bloques, con margen temporal entre *folds*.
2. **Ventanas solapadas.** El solapamiento se aplica después de partir, no antes.
3. **ICA o filtros adaptativos ajustados sobre el registro completo.** Es fuga. Un filtro fijo (FIR o IIR con coeficientes no estimados de los datos) es discutible pero acotado; se documenta la decisión.
4. **Hiperparámetros elegidos sobre la misma partición de evaluación.** Requiere *nested cross-validation*.
5. **Normalización con estadísticos globales del dataset.** El conjunto de prueba contribuyó a definirlos.

**REGLA DURA para asistentes.** Si un experimento propuesto cae en cualquiera de estos modos, se señala antes de escribir el código.

### Reporte

- **Nivel de azar empírico**, estimado por permutaciones: con pocos ensayos y clases desbalanceadas, el teórico no sirve (Combrisson & Jerbi, 2015).
- **Intervalos de confianza**, no solo la media: con pocos sujetos, la varianza del estimador domina (Varoquaux, 2018).
- Se declaran el tipo de partición, el número de *folds* y el de sujetos.

## Lista de verificación

- [ ] Nada escribe en `data/raw/`.
- [ ] Cada script de experimento llama a `set_seed()` y guarda el `RunContext`.
- [ ] Todo ajuste ocurre dentro del *pipeline* y solo con entrenamiento.
- [ ] La partición es por sujeto o por bloques, con margen temporal si aplica.
- [ ] El reporte trae nivel de azar empírico e intervalo de confianza.

## Referencias

Combrisson, E., & Jerbi, K. (2015). Exceeding chance level by chance: The caveat of theoretical chance levels in brain signal classification and statistical assessment of decoding accuracy. *Journal of Neuroscience Methods, 250*, 126–136. https://doi.org/10.1016/j.jneumeth.2015.01.010

Pernet, C. R., Appelhoff, S., Gorgolewski, K. J., Flandin, G., Phillips, C., Delorme, A., & Oostenveld, R. (2019). EEG-BIDS, an extension to the brain imaging data structure for electroencephalography. *Scientific Data, 6*, 103. https://doi.org/10.1038/s41597-019-0104-8

Varoquaux, G. (2018). Cross-validation failure: Small sample sizes lead to large error bars. *NeuroImage, 180*, 68–77. https://doi.org/10.1016/j.neuroimage.2017.06.061

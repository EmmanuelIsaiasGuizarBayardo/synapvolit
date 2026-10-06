<!-- Archivo del estandar DUNNE, generado por la plantilla. No se edita aqui:
     se actualiza con 'uvx copier update --trust'. -->

# Módulo: datos de personas

Aplica porque el proyecto capta señales o datos de personas, aunque no los guarde.

- **REGLA DURA.** El README declara qué se capta, de quién, dónde vive y cuánto dura. `tests/test_gobernanza.py` falla mientras la declaración tenga marcas `[COMPLETAR]`.
- En protección de datos, el tratamiento incluye captar y usar, no solo almacenar: una señal efímera también es un tratamiento.
- **PREFERENCIA.** Si el proyecto requiere un aviso de privacidad lo determina el área de protección de datos de la universidad, no este estándar. El README registra quién lo revisó y cuándo, o que está pendiente.
- **REGLA DURA para asistentes.** Si un cambio propuesto empieza a escribir a disco, enviar por red o registrar datos de personas, se señala antes de escribir el código, porque vuelve falsa la declaración del README.

## Lista de verificación

- [ ] La declaración del README describe lo que el código hace hoy.
- [ ] Ningún componente nuevo persiste o transmite datos de personas sin actualizarla.

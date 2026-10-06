<!-- Archivo del estandar DUNNE, generado por la plantilla. No se edita aqui:
     se actualiza con 'uvx copier update --trust'. -->

# Módulo: operación en vivo

Aplica porque el proyecto se opera frente a público, con alguien a cargo. En este
módulo son reglas duras las que, si se violan, fallan frente al público.

## Arrancar siempre

- **REGLA DURA.** La aplicación arranca aunque falten datos, hardware o red, y en lugar de fallar muestra qué falta y con qué comando se resuelve. Que arranque siempre importa más que que arranque completa.
- **PREFERENCIA.** Un solo comando de verificación previa revisa cada requisito del montaje (archivos, red, puertos, permisos) y lo reporta en lenguaje de operador antes de levantar la aplicación.
- **PREFERENCIA.** El modo por omisión es el de operación. Los modos de desarrollo, como la recarga automática, se activan de forma explícita.

## Estados que se pueden actuar

- **REGLA DURA.** Cada estado que ve el operador trae, además del diagnóstico, una instrucción concreta. "Contacto pobre" no sirve bajo presión; "aparta el cabello de la frente y revisa el clip del lóbulo", sí. Es el principio de la gestión de alarmas industrial: una alarma señala una condición que exige una respuesta (International Society of Automation [ISA], 2016).
- **REGLA DURA.** Una prueba recorre todos los estados que el código puede producir y falla si alguno no tiene instrucción. Si el proyecto tiene contenido didáctico, las instrucciones viven en `content/`. El patrón, a adaptar:

```python
def test_cada_estado_tiene_instruccion() -> None:
    instrucciones = cargar_contenido()["estados"]
    faltan = [e.value for e in Estado if e.value not in instrucciones]
    assert not faltan, f"Estados sin instrucción para el operador: {faltan}"
```

## Lo que ve el público

- **REGLA DURA.** Lo que se muestra nunca aparenta ser lo que no es. Una dilatación temporal, una señal simulada o amplificada, o datos de demostración se declaran en pantalla mientras están activos.
- Lo que es solo para el personal no aparece en el modo público.
- **PREFERENCIA.** Todo enlace o código QR impreso apunta, con una ruta corta, a un dominio que controla la organización; nunca a una URL que cambie al mover el repositorio.

## Guía del operador

- **REGLA DURA.** `docs/operacion.md` explica el montaje, la lista de verificación previa al evento, qué hacer ante cada estado y el cierre. Se escribe para alguien que no estuvo en el desarrollo, porque los operadores rotan.

## Lista de verificación

- [ ] La aplicación arranca sin datos, sin hardware y sin red, y dice qué falta.
- [ ] Cada estado tiene instrucción, y una prueba lo verifica.
- [ ] Toda simulación, dilatación o amplificación se declara en pantalla.
- [ ] `docs/operacion.md` coincide con el montaje real.

## Referencias

International Society of Automation. (2016). *ANSI/ISA-18.2-2016: Management of alarm systems for the process industries*. ISA.

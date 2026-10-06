"""Métricas como consultas puras sobre el registro de eventos.

**Minutos efectivos** = medida de (ejercicio ∩ señal válida) − pausas, donde:

* *ejercicio*: de cada ``ejercicio_inicio`` a su ``ejercicio_fin`` (por ``id``). Uno sin fin
  se cierra en el siguiente evento de la sesión que lo interrumpe o en ``sesion_fin``.
* *señal válida*: de cada ``senal`` con ``valida = true`` al siguiente con ``false``. La sesión
  empieza sin señal válida.
* *pausas*: de ``pausa`` a ``reanudar`` (la ayuda abierta, por ejemplo).

Así un ejercicio con el brazalete despegado o con el juego en pausa no cuenta, y el tiempo entre
ejercicios tampoco. La adherencia es efectivos / prescritos.
"""

from __future__ import annotations

from .fatiga import indice_fatiga

Intervalos = list[tuple[float, float]]


def unir(iv: Intervalos) -> Intervalos:
    """Une intervalos que se tocan o se enciman; el resultado está ordenado y es disjunto."""
    salida: Intervalos = []
    for a, b in sorted(i for i in iv if i[1] > i[0]):
        if salida and a <= salida[-1][1]:
            salida[-1] = (salida[-1][0], max(salida[-1][1], b))
        else:
            salida.append((a, b))
    return salida


def interseccion(x: Intervalos, y: Intervalos) -> Intervalos:
    """Intersección de dos uniones de intervalos (barrido lineal sobre listas ordenadas)."""
    x, y = unir(x), unir(y)
    i = j = 0
    salida: Intervalos = []
    while i < len(x) and j < len(y):
        a, b = max(x[i][0], y[j][0]), min(x[i][1], y[j][1])
        if a < b:
            salida.append((a, b))
        if x[i][1] < y[j][1]:
            i += 1
        else:
            j += 1
    return salida


def restar(x: Intervalos, y: Intervalos) -> Intervalos:
    """``x`` sin lo que cubre ``y``."""
    salida, y = [], unir(y)
    for a, b in unir(x):
        for c, d in y:
            if d <= a or c >= b:
                continue
            if c > a:
                salida.append((a, c))
            a = max(a, d)
        if a < b:
            salida.append((a, b))
    return salida


def medida(iv: Intervalos) -> float:
    return sum(b - a for a, b in unir(iv))


def _tramos(eventos: list[dict], fin: float) -> tuple[Intervalos, Intervalos, Intervalos]:
    ejercicios, senal, pausas = [], [], []
    abierto: dict[int, float] = {}
    senal_desde = pausa_desde = None
    for e in eventos:
        tipo, t = e["tipo"], e["t"]
        if tipo == "ejercicio_inicio":
            for k in list(abierto):  # un inicio nuevo cierra cualquier ejercicio que quedó abierto
                ejercicios.append((abierto.pop(k), t))
            abierto[e["id"]] = t
        elif tipo == "ejercicio_fin" and e.get("id") in abierto:
            ejercicios.append((abierto.pop(e["id"]), t))
        elif tipo == "senal":
            if e["valida"] and senal_desde is None:
                senal_desde = t
            elif not e["valida"] and senal_desde is not None:
                senal.append((senal_desde, t))
                senal_desde = None
        elif tipo == "pausa" and pausa_desde is None:
            pausa_desde = t
        elif tipo == "reanudar" and pausa_desde is not None:
            pausas.append((pausa_desde, t))
            pausa_desde = None
    ejercicios += [(t0, fin) for t0 in abierto.values()]
    if senal_desde is not None:
        senal.append((senal_desde, fin))
    if pausa_desde is not None:
        pausas.append((pausa_desde, fin))
    return ejercicios, senal, pausas


def resumen(eventos: list[dict], minutos_prescritos: float = 30.0) -> dict:
    """Minutos efectivos, adherencia, conteos y fatiga, calculados solo desde los eventos."""
    if not eventos:
        return {}
    fin = eventos[-1]["t"]
    ejercicios, senal, pausas = _tramos(eventos, fin)
    efectivos = medida(restar(interseccion(ejercicios, senal), pausas)) / 60.0
    finales = [e for e in eventos if e["tipo"] == "ejercicio_fin"]
    cuenta = {
        r: sum(e.get("resultado") == r for e in finales)
        for r in ("acierto", "fallo", "tiempo", "interrumpido")
    }
    return {
        "minutos_sesion": round(fin / 60.0, 2),
        "minutos_en_ejercicio": round(medida(ejercicios) / 60.0, 2),
        "minutos_senal_valida": round(medida(senal) / 60.0, 2),
        "minutos_pausa": round(medida(pausas) / 60.0, 2),
        "minutos_efectivos": round(efectivos, 2),
        "minutos_prescritos": minutos_prescritos,
        "adherencia": round(efectivos / minutos_prescritos, 3) if minutos_prescritos > 0 else None,
        "ejercicios": len(finales),
        **{f"{r}s" if r != "tiempo" else "sin_respuesta": n for r, n in cuenta.items()},
        "fatiga": indice_fatiga(eventos),
    }

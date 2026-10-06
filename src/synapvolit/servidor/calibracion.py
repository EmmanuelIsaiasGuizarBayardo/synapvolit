"""Máquina de estados de la calibración guiada (pura: recibe el tiempo, no lo lee).

Secuencia, que coincide con los seis pasos de la pantalla del juego::

    contacto → reposo → [preparar → contracción → descanso] × repeticiones × movimientos → lista

* **Contacto**: espera a que todos los canales tengan contacto evaluado y no malo durante
  ``contacto_s`` seguidos. Si no ocurre en ``espera_contacto_s``, termina en error y dice qué canal.
* **Reposo** y **contracción** registran la envolvente (una muestra por paso del bucle, ~100 Hz).
  Preparar y descanso solo cuentan tiempo.
* Si la señal deja de estar fresca más de ``max_sin_senal_s`` mientras se registra, termina en
  error: una calibración con huecos largos no es confiable.
* Al final calcula la matriz con ``procesamiento.calibrar``, que es la misma función del modo
  fuera de línea, y advierte si algún movimiento apenas supera su reposo.

Como recibe el tiempo en cada llamada, se prueba con un reloj falso y tiempos exactos (estándar
DUNNE, señal externa).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..clasificacion import ModeloLDA, entrenar, evaluar
from ..procesamiento import MALO, MOVIMIENTOS, SIN_EVALUAR, MatrizCalibracion, calibrar

INACTIVA, CONTACTO, REPOSO, PREPARAR, CONTRACCION, DESCANSO = (
    "inactiva",
    "contacto",
    "reposo",
    "preparar",
    "contraccion",
    "descanso",
)
CALCULANDO, LISTA, ERROR, CANCELADA = "calculando", "lista", "error", "cancelada"
TERMINALES = (INACTIVA, LISTA, ERROR, CANCELADA)
# Los descansos se registran con su propia etiqueta: la matriz los ignora (su reposo es solo el
# reposo inicial), pero el clasificador los usa como más ejemplos de reposo, repartidos en toda
# la sesión, para que la validación por repeticiones tenga reposo en cada partición.
DESCANSO_ETQ = 5
VERIF_EXACTITUD = 0.8
VERBO = {
    "extension": "extiende la muñeca",
    "flexion": "dobla la muñeca hacia abajo",
    "pronacion": "gira la palma hacia abajo",
    "supinacion": "gira la palma hacia arriba",
}


@dataclass(frozen=True)
class Protocolo:
    """Duraciones y orden de la calibración (los valores por defecto duran ~1.7 min)."""

    movimientos: tuple[int, ...] = (0, 1, 2, 3)  # índices en MOVIMIENTOS
    repeticiones: int = 3
    reposo_s: float = 5.0
    preparar_s: float = 2.0
    contraccion_s: float = 3.0
    descanso_s: float = 3.0
    contacto_s: float = 1.0
    espera_contacto_s: float = 15.0
    max_sin_senal_s: float = 1.5
    relacion_minima: float = 2.0  # referencia / reposo por debajo de esto: advertencia

    @property
    def duracion_s(self) -> float:
        por_rep = self.preparar_s + self.contraccion_s + self.descanso_s
        return self.contacto_s + self.reposo_s + por_rep * self.repeticiones * len(self.movimientos)


# Verificación de un perfil guardado: una repetición corta de cada movimiento (~23 s)
VERIFICACION = Protocolo(
    repeticiones=1, reposo_s=4.0, preparar_s=1.5, contraccion_s=2.0, descanso_s=1.0
)


class MaquinaCalibracion:
    """Calibración guiada; el bucle de la sesión llama a ``avanzar`` en cada paso."""

    def __init__(self, canales: int, tasa_hz: float = 100.0) -> None:
        self.canales, self.tasa = canales, tasa_hz
        self.fase = INACTIVA
        self.p = Protocolo()
        self.matriz: MatrizCalibracion | None = None
        self.modelo: ModeloLDA | None = None
        self.calculo_externo = False  # True: la sesión corre ``calcular`` fuera del bucle
        self.modo = "completa"
        self.verificacion: dict | None = None
        self._verificar: tuple | None = None
        self.mensaje = "Lista para calibrar"
        self.advertencias: list[str] = []
        self.i_mov = self.rep = 0
        self._t_fase = 0.0
        self._dur = 0.0
        self._t_contacto: float | None = None
        self._t_sin_senal: float | None = None
        self._n = 0
        self._env = self._val = self._etq = self._ras = self._rv = None

    # ---- órdenes ----
    def iniciar(self, protocolo: Protocolo, t: float, verificar: tuple | None = None) -> None:
        """Empieza una calibración completa o, con ``verificar=(matriz, modelo)``, una verificación.

        La verificación sigue el mismo guion corto y, en vez de entrenar, mide qué tan bien el
        perfil guardado explica la señal de hoy (ver ``calcular``).
        """
        self.p, self.advertencias, self.i_mov, self.rep = protocolo, [], 0, 0
        self._verificar, self.verificacion = verificar, None
        self.modo = "verificar" if verificar is not None else "completa"
        cap = (
            int(
                (
                    protocolo.reposo_s
                    + (protocolo.contraccion_s + protocolo.descanso_s)
                    * protocolo.repeticiones
                    * len(protocolo.movimientos)
                )
                * self.tasa
                * 1.5
            )
            + 64
        )
        self._env = np.zeros((cap, self.canales), np.float32)
        self._val = np.zeros((cap, self.canales), bool)
        self._etq = np.zeros(cap, np.int8)
        self._ras = np.zeros((cap, 2 * self.canales), np.float32)
        self._rv = np.zeros(cap, bool)
        self._con_rasgos = False
        self.matriz = self.modelo = None
        self._n = 0
        self._t_contacto = None
        self._ir(CONTACTO, t, protocolo.espera_contacto_s, "Revisando los sensores")

    def reiniciar(self) -> None:
        """Vuelve a inactiva sin resultado (al cambiar de paciente no sobrevive nada anterior)."""
        self.fase, self.mensaje, self.matriz, self.modelo = (
            INACTIVA,
            "Lista para calibrar",
            None,
            None,
        )
        self.verificacion, self.advertencias, self._dur = None, [], 0.0

    def cancelar(self, t: float) -> None:
        if self.fase not in TERMINALES:
            self._ir(CANCELADA, t, 0.0, "Calibración cancelada")

    # ---- estado para la interfaz ----
    @property
    def movimiento(self) -> str | None:
        if self.fase in (PREPARAR, CONTRACCION, DESCANSO):
            return MOVIMIENTOS[self.p.movimientos[self.i_mov]]
        return None

    @property
    def paso(self) -> int:
        """Paso de la pantalla del juego: 1 contacto, 2 reposo, 3-6 cada movimiento."""
        if self.fase == CONTACTO:
            return 1
        if self.fase == REPOSO:
            return 2
        if self.movimiento is not None:
            return 3 + self.p.movimientos[self.i_mov]
        return 7 if self.fase in (CALCULANDO, LISTA) else 0

    @property
    def objetivo(self) -> int:
        """Clase que el paciente debería estar haciendo ahora (0 reposo, 1-4 movimientos)."""
        return self.p.movimientos[self.i_mov] + 1 if self.fase == CONTRACCION else 0

    def progreso(self, t: float) -> tuple[float, float]:
        """(fracción de la fase, segundos restantes)."""
        if self._dur <= 0:
            return 1.0, 0.0
        e = min(t - self._t_fase, self._dur)
        return e / self._dur, self._dur - e

    # ---- bucle ----
    def avanzar(
        self,
        t: float,
        env_uv: np.ndarray,
        valida: np.ndarray,
        calidad: np.ndarray,
        fresca: bool,
        rasgos: np.ndarray | None = None,
        rasgos_validos: bool = False,
    ) -> bool:
        """Un paso del bucle. Devuelve ``True`` si cambió de fase (para avisar a la interfaz)."""
        f = self.fase
        if f in TERMINALES or f == CALCULANDO:
            return False
        if f == CONTACTO:
            bien = fresca and bool(np.all((calidad != MALO) & (calidad != SIN_EVALUAR)))
            if not bien:
                self._t_contacto = None
            elif self._t_contacto is None:
                self._t_contacto = t
            if self._t_contacto is not None and t - self._t_contacto >= self.p.contacto_s:
                return self._ir(REPOSO, t, self.p.reposo_s, "Relaja la mano sobre la mesa")
            if t - self._t_fase >= self._dur:
                malos = [
                    MOVIMIENTOS[c] for c in range(self.canales) if calidad[c] in (MALO, SIN_EVALUAR)
                ]
                que = f"canal de {', '.join(malos)}" if malos else "la señal"
                return self._fallar(t, f"Sin contacto estable en {que}: revisa los electrodos")
            return False
        if f in (REPOSO, CONTRACCION, DESCANSO):
            if not fresca:
                self._t_sin_senal = t if self._t_sin_senal is None else self._t_sin_senal
                if t - self._t_sin_senal > self.p.max_sin_senal_s:
                    return self._fallar(
                        t, "Se perdió la señal del brazalete durante la calibración"
                    )
            else:
                self._t_sin_senal = None
                self._registrar(
                    env_uv,
                    valida & (calidad != MALO),
                    self.objetivo if f == CONTRACCION else DESCANSO_ETQ if f == DESCANSO else 0,
                    rasgos,
                    rasgos_validos,
                )
        if t - self._t_fase < self._dur:
            return False
        # la fase siguiente empieza en su hora programada, no en el paso en que se detectó:
        # así el retraso de un paso no se acumula a lo largo de las ~25 fases
        return self._siguiente(self._t_fase + self._dur)

    # ---- interno ----
    def _registrar(
        self,
        env: np.ndarray,
        val: np.ndarray,
        etiqueta: int,
        rasgos: np.ndarray | None = None,
        rasgos_validos: bool = False,
    ) -> None:
        if self._n < len(self._etq):
            self._env[self._n], self._val[self._n], self._etq[self._n] = env, val, etiqueta
            if rasgos is not None:
                self._ras[self._n], self._rv[self._n] = rasgos, rasgos_validos
                self._con_rasgos = True
            self._n += 1

    def _separar(
        self,
    ) -> None:  # marca el fin de una repetición para que no se fusione con la siguiente
        self._registrar(np.zeros(self.canales), np.zeros(self.canales, bool), -1)

    def _siguiente(self, t: float) -> bool:
        p, f = self.p, self.fase
        if f == REPOSO:
            self._separar()
            return self._preparar(t)
        if f == PREPARAR:
            return self._ir(
                CONTRACCION,
                t,
                p.contraccion_s,
                f"¡{VERBO[self.movimiento].capitalize()} con fuerza!",
            )
        if f == CONTRACCION:
            self._separar()
            return self._ir(DESCANSO, t, p.descanso_s, "Descansa")
        # fin del descanso: siguiente repetición o siguiente movimiento
        self.rep += 1
        if self.rep >= p.repeticiones:
            self.rep, self.i_mov = 0, self.i_mov + 1
        if self.i_mov >= len(p.movimientos):
            return self._calcular(t)
        return self._preparar(t)

    def _preparar(self, t: float) -> bool:
        return self._ir(
            PREPARAR, t, self.p.preparar_s, f"Prepárate: {VERBO[self.movimiento_siguiente]}"
        )

    @property
    def movimiento_siguiente(self) -> str:
        return MOVIMIENTOS[self.p.movimientos[self.i_mov]]

    def _calcular(self, t: float) -> bool:
        self._ir(CALCULANDO, t, 0.0, "Calculando")
        if self.calculo_externo:  # la sesión lo corre en un hilo y llama a ``terminar``
            return True
        return self.terminar(t, self.calcular())

    def calcular(self) -> tuple[MatrizCalibracion | None, ModeloLDA | None, str | None, list[str]]:
        """Parte pesada: matriz y LDA. Solo lee el registro, así que puede correr en otro hilo.

        Returns
        -------
        (matriz, modelo, error, advertencias)
        """
        n, avisos = self._n, []
        if self._verificar is not None:
            return self._comparar(avisos)
        try:
            m = calibrar(self._env[:n], self._val[:n], self._etq[:n])
        except ValueError as e:
            return None, None, f"No se pudo calibrar: {e}", avisos
        ref = m.referencia_uv
        for i in self.p.movimientos:
            c = m.agonista[i]
            if ref[c] < self.p.relacion_minima * m.reposo_uv[c]:
                avisos.append(
                    f"{MOVIMIENTOS[i]}: el canal apenas supera su reposo "
                    f"({ref[c] / m.reposo_uv[c]:.1f}×)"
                )
        modelo = None
        if self._con_rasgos:  # el clasificador se entrena con los mismos datos y la misma cadena
            etq = np.where(self._rv[:n], self._etq[:n], -1).astype(np.int8)
            try:
                modelo = entrenar(self._ras[:n], etq, self.tasa)
            except ValueError as e:
                return None, None, f"No se pudo entrenar el clasificador: {e}", avisos
        return m, modelo, None, avisos

    def _comparar(self, avisos: list[str]) -> tuple:
        """Verificación: ¿el perfil guardado sigue describiendo la señal de hoy?

        Dos criterios, porque fallan por razones distintas:
        * exactitud del LDA guardado sobre los datos de hoy (≥ 80%): si cambió la colocación de los
          electrodos, el patrón entre canales cambia y el modelo deja de acertar;
        * razón entre la referencia de hoy y la guardada en cada canal agonista (0.5 a 2): una piel
          más seca o un electrodo más lejos cambian la amplitud y desajustan la intensidad.
        """
        guardada, modelo = self._verificar
        n = self._n
        try:
            nueva = calibrar(self._env[:n], self._val[:n], self._etq[:n])
        except ValueError:  # ningún canal sube en su movimiento: casi seguro, electrodos movidos
            nueva = None
        etq = np.where(self._rv[:n], self._etq[:n], -1).astype(np.int8)
        exactitud = evaluar(modelo, self._ras[:n], etq, self.tasa) if self._con_rasgos else 0.0
        if nueva is None:
            razon = np.zeros(len(guardada.reposo_uv))
        else:
            razon = nueva.referencia_uv / guardada.referencia_uv
        fuera = [
            MOVIMIENTOS[m] for m, c in enumerate(guardada.agonista) if not 0.5 <= razon[c] <= 2.0
        ]
        ok = exactitud >= VERIF_EXACTITUD and not fuera
        self.verificacion = {
            "ok": ok,
            "exactitud": round(exactitud, 3),
            "razon_amplitud": [round(float(r), 2) for r in razon],
        }
        if ok:
            return guardada, modelo, None, avisos
        motivos = (
            [f"exactitud {exactitud:.0%} (mínimo {VERIF_EXACTITUD:.0%})"]
            if exactitud < VERIF_EXACTITUD
            else []
        )
        motivos += [f"amplitud distinta en {', '.join(fuera)}"] if fuera else []
        texto = f"El perfil no pasó la verificación ({'; '.join(motivos)})"
        return None, None, texto + ": haz la calibración completa", avisos

    def terminar(self, t: float, resultado: tuple) -> bool:
        """Aplica el resultado de ``calcular`` (si la calibración no se canceló mientras tanto)."""
        if self.fase != CALCULANDO:
            return False
        m, modelo, error, avisos = resultado
        self.advertencias = avisos
        if error:
            return self._fallar(t, error)
        self.matriz, self.modelo = m, modelo
        texto = (
            "¡Listo! Perfil verificado" if self.modo == "verificar" else "¡Listo! Sensor calibrado"
        )
        return self._ir(LISTA, t, 0.0, texto)

    def _fallar(self, t: float, motivo: str) -> bool:
        return self._ir(ERROR, t, 0.0, motivo)

    def _ir(self, fase: str, t: float, dur: float, mensaje: str) -> bool:
        self.fase, self._t_fase, self._dur, self.mensaje = fase, t, dur, mensaje
        return True

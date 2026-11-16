"""Empilhador: junta, dentro de uma BP, as pilhas soltas dos itens escolhidos.

Um aperto do atalho faz uma rodada: enquanto houver duas pilhas incompletas do
mesmo item, arrasta a de trás para cima da da frente, e termina quando não
sobrar o que juntar. Cada arrasto pede o mouse com a prioridade mais baixa, então
macros, cura e loot passam na frente entre um arrasto e outro.
"""
from __future__ import annotations

import logging
import threading
import time

import numpy as np

from . import loot
from .action_manager import drag_item, priority

logger = logging.getLogger(__name__)

MAX_STEPS = 30
CHECK_SECONDS = 0.05
STABLE_READS = 2
# Com o jogo na frente o arrasto usa o cursor real: só começa com o mouse parado esse tempo.
IDLE_SECONDS = 1.5
IDLE_POLL = 0.1
IDLE_GIVE_UP = 20.0

# Número da pilha: branco com contorno preto, alinhado à direita no pé do slot.
# A pilha máxima é 100, e só número de três algarismos começa tão à esquerda.
DIGIT_ROWS = slice(18, 30)
FULL_FIRST_COLUMN = 13
DIGIT_WHITE = 200
OUTLINE_DARK = 40


def is_full(pixels) -> bool:
    """True se o número da pilha tem três algarismos (100, o máximo)."""
    if pixels.shape[0] < loot.SLOT:
        return False
    corner = pixels[DIGIT_ROWS].astype(np.int16)
    white = corner.min(axis=2) >= DIGIT_WHITE
    dark = corner.max(axis=2) <= OUTLINE_DARK
    outlined = np.zeros_like(dark)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            outlined |= np.roll(np.roll(dark, dy, axis=0), dx, axis=1)
    columns = np.flatnonzero((white & outlined).any(axis=0))
    return len(columns) > 0 and int(columns[0]) <= FULL_FIRST_COLUMN


def group_of(pixels, groups) -> int | None:
    """Qual item escolhido está no slot (cada item pode ter vários desenhos)."""
    if loot.is_empty(pixels):
        return None
    for index, sprites in enumerate(groups):
        if loot.is_known(pixels, sprites):
            return index
    return None


def open_stacks(view, groups, group: int) -> list:
    return [slot for slot in view
            if group_of(slot.pixels, groups) == group and not is_full(slot.pixels)]


def describe(view, groups) -> str:
    """Resumo do que a BP tem, para o log: o porquê de juntar ou não."""
    parts = []
    for group in range(len(groups)):
        found = [slot for slot in view if group_of(slot.pixels, groups) == group]
        full = sum(1 for slot in found if is_full(slot.pixels))
        parts.append(f"item {group + 1}: {len(found) - full} aberta(s), {full} cheia(s)")
    others = sum(1 for slot in view if not loot.is_empty(slot.pixels) and group_of(slot.pixels, groups) is None)
    summary = "; ".join(parts) or "nenhum item escolhido"
    if others:
        summary += f"; {others} slot(s) com itens fora da lista"
    return summary


def plan(view, groups):
    """(de, para, item) da próxima junção, ou None se não há o que juntar.

    Junta a última pilha incompleta na primeira: o que sobrar fica atrás."""
    for group in range(len(groups)):
        stacks = open_stacks(view, groups, group)
        if len(stacks) >= 2:
            return stacks[-1], stacks[0], group
    return None


class Stacker:
    def __init__(self, profile: dict, log=logger.info, get_frame=lambda: None, alert=None):
        self.am = None
        self.profile = profile
        self.config = profile["stacker"]
        self.log = log
        self.get_frame = get_frame
        self.alert = alert or log
        self.merged = 0
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop_event.is_set())

    def missing(self) -> str:
        if not self.config["grid"]:
            return "os slots da BP"
        if not self.config["items"]:
            return "os itens"
        return ""

    def start(self) -> bool:
        if self.is_running or self.am is None or self.missing():
            return False
        self.merged = 0
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="pilhas")
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive() and self._thread is not threading.current_thread():
            self._thread.join(timeout=3)

    # ---------- leitura ----------

    def _read(self):
        frame = self.get_frame()
        if frame is None or not loot.window_open(frame, self.config["grid"]):
            return None
        return loot.read_slots(frame, self.config["grid"])

    def _server_wait(self) -> float:
        try:
            return max(0.0, float(self.profile["input"]["server_wait"]))
        except (TypeError, ValueError):
            return 2.0

    def _settled_change(self, before):
        """A BP depois de mudar e parar de mudar; None se não mudou a tempo."""
        deadline = time.monotonic() + self._server_wait()
        view, changed, same = before, False, 0
        while time.monotonic() < deadline:
            if self._stop_event.wait(CHECK_SECONDS):
                return None
            after = self._read()
            if after is None:
                return None
            if loot.view_changed(view, after):
                view, changed, same = after, True, 0
            elif changed:
                same += 1
                if same >= STABLE_READS:
                    break
        return view if changed else None

    # ---------- mouse ----------

    def _wait_idle_mouse(self) -> bool:
        """Espera o mouse da pessoa ficar parado. False se desistiu ou pararam."""
        give_up = time.monotonic() + IDLE_GIVE_UP
        last = self.am.get_cursor()
        still_since = time.monotonic()
        while not self._stop_event.is_set():
            now = time.monotonic()
            if now - still_since >= IDLE_SECONDS:
                return True
            if now > give_up:
                self.log("Pilhas: seu mouse não ficou parado e desisti. Aperte de novo.")
                return False
            self._stop_event.wait(IDLE_POLL)
            position = self.am.get_cursor()
            if position != last:
                last, still_since = position, time.monotonic()
        return False

    def _drag(self, source, target) -> bool:
        start = (source.left + loot.SLOT // 2, source.top + loot.SLOT // 2)
        end = (target.left + loot.SLOT // 2, target.top + loot.SLOT // 2)
        with self.am.guarded() as held:
            if not held:
                self.log("Pilhas: não foi possível segurar o mouse.")
                return False
            # Jogo atrás: só mensagem, sem trazer o jogo nem mexer no seu mouse.
            # Jogo na frente: pelo cursor (mensagem não é confiável aí).
            return bool(drag_item(self.am, start, end, background=True, quick=True))

    # ---------- rodada ----------

    def _step(self) -> bool:
        view = self._read()
        if view is None:
            if self.am.is_minimized():
                self.log("Pilhas: o jogo está minimizado e o Windows não desenha janela minimizada, "
                         "então não dá para ver a BP. Deixe o jogo atrás de outra janela, sem minimizar.")
            else:
                self.log("Pilhas: não vi a BP nos slots salvos.")
            return False
        step = plan(view, self.config["items"])
        if step is None:
            if not self.merged:
                self.log("Pilhas: nada a juntar (" + describe(view, self.config["items"]) + "). "
                         "Tamanhos do mesmo item precisam estar no mesmo item: use + tamanho.")
            return False
        source, target, group = step
        # Só o cursor mexe no seu mouse: com o jogo atrás vai por mensagem e não precisa esperar.
        if self.am.is_foreground() and not self._wait_idle_mouse():
            return False
        # Nada de mouse enquanto outro módulo usa: a espera acima pode ter deixado a BP velha.
        view = self._read()
        step = plan(view, self.config["items"]) if view is not None else None
        if step is None:
            return False
        source, target, group = step
        before = len(open_stacks(view, self.config["items"], group))
        if not self._drag(source, target):
            return False
        after = self._settled_change(view)
        if after is None or len(open_stacks(after, self.config["items"], group)) >= before:
            if not self._stop_event.is_set():
                self.alert("Pilhas: arrastei e as pilhas não se juntaram. Esse item empilha?")
            return False
        self.merged += 1
        return True

    def _run(self) -> None:
        try:
            with priority("stacker"):
                for _ in range(MAX_STEPS):
                    if self._stop_event.is_set() or not self._step():
                        break
            self.log(f"Pilhas: {self.merged} junção(ões).")
        except Exception:
            logger.exception("Erro no empilhador")
        finally:
            self._stop_event.set()

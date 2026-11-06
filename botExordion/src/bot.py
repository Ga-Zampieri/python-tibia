"""Controlador do bot: toda a lógica, sem nada de interface.

A UI lê `status()`, chama os métodos públicos e consome `events`. Nenhuma thread
daqui toca em widget.
"""
from __future__ import annotations

import logging
import queue
import threading
import time

from . import battle_vision
from .action_manager import ActionManager, key_to_vk
from .alarm import AlarmMonitor
from .auto_hotkey import AutoHotkey
from .capture import capture_client
from .click_capture import ClickCapture
from .fishing import Pesca
from .hotkey_service import HotkeyService
from .macros import MacroRunner
from .rune_maker import RuneMaker
from .settings import ProfileStore
from .status import Status
from .survival import Survival
from .training import AttackPlanner, TrainingMode, TrainingStateMachine
from .window_handler import getWindows, pick_game_window

logger = logging.getLogger(__name__)

BATTLE_SCAN_SECONDS = 1.5
BARS_SCAN_SECONDS = 0.5
WINDOW_SCAN_SECONDS = 2.0
CAPTURE_TIMEOUT_SECONDS = 30


def beep() -> None:
    import winsound
    for _ in range(3):
        winsound.Beep(1200, 250)


class BotController:
    def __init__(self, store=None, capture=capture_client, list_windows=getWindows):
        self.store = store or ProfileStore()
        self._capture_frame = capture
        self._list_windows = list_windows
        self.events = queue.Queue()
        self.am = None

        self.training_on = False
        self.macros_on = False
        self.alarm_on = False
        self.survival_on = False
        self.hp = None
        self.mana = None
        self.target_count = 0
        self.training_started_at = None
        self._click_capture = None

        self._actions = queue.Queue(maxsize=8)
        self._shutdown = threading.Event()
        self._next_battle = 0.0
        self._next_bars = 0.0
        self._next_window_scan = 0.0
        self._hotkeys = HotkeyService(self.on_key)

        self.alarm = AlarmMonitor()
        self.repeater = AutoHotkey()
        self.profile_name = ""
        self.profile = {}
        name, profile = self.store.load_last()
        self._use_profile(name, profile)

    # ---------- ciclo de vida ----------

    def start(self) -> None:
        self._hotkeys.start()
        threading.Thread(target=self._action_loop, daemon=True, name="acoes").start()
        threading.Thread(target=self._vision_loop, daemon=True, name="visao").start()

    def shutdown(self) -> None:
        self.stop_all(announce=False)
        self._shutdown.set()
        self._hotkeys.stop()
        self.save()

    def log(self, message: str) -> None:
        logger.info(message)
        self.events.put(("log", message))

    def _emit_prompt(self, text) -> None:
        self.events.put(("prompt", text))

    def save(self) -> None:
        self.store.save(self.profile_name, self.profile)

    # ---------- perfis ----------

    def _use_profile(self, name: str, profile: dict) -> None:
        self.profile_name = name
        self.profile = profile
        self.macros = MacroRunner(profile, self.log)
        self.fishing = Pesca(profile["fishing"])
        self.machine = TrainingStateMachine(mode=TrainingMode(profile["training"]["mode"]))
        self.planner = AttackPlanner(self.machine)
        self.survival = Survival(profile["survival"], self.run_action)
        self.rune_maker = RuneMaker(profile["rune_maker"], lambda: self.mana, self.log)
        self._set_action_manager(self.am)
        self.store.remember_last(name)

    def switch_profile(self, name: str) -> None:
        self.stop_all(announce=False)
        self.save()
        self._use_profile(name, self.store.load(name))
        self.log(f"Perfil: {name}")

    def create_profile(self, name: str) -> None:
        name = name.strip()
        if not name:
            return
        self.store.save(name, self.profile)
        self.switch_profile(name)

    def delete_profile(self) -> bool:
        others = [name for name in self.store.names() if name != self.profile_name]
        if not others:
            self.log("Este é o único perfil.")
            return False
        doomed = self.profile_name
        self.switch_profile(others[0])
        self.store.delete(doomed)
        return True

    # ---------- janela ----------

    def _set_action_manager(self, am) -> None:
        self.am = am
        for module in (self.macros, self.fishing, self.survival, self.rune_maker):
            module.am = am

    def attach(self, hwnd: int, remember: bool = True) -> bool:
        am = ActionManager(hwnd)
        if not am.is_valid():
            self.log("Essa janela não existe mais.")
            return False
        self.stop_all(announce=False)
        self._set_action_manager(am)
        if remember:
            self.profile["window_title"] = am.title()
        self._migrate_legacy_coords()
        self.save()
        self.log(f"Conectado a: {am.title()}")
        return True

    def _migrate_legacy_coords(self) -> None:
        """Os mapeamentos antigos estão em coordenadas de tela; converte uma vez."""
        if not self.profile["legacy_screen_coords"] or self.am.is_minimized():
            return

        def convert(point):
            return list(self.am.screen_to_client(point)) if point else point

        self.profile["player_position"] = convert(self.profile["player_position"])
        for macro in self.profile["macros"].values():
            macro["pos"] = convert(macro["pos"])
            macro["end"] = convert(macro.get("end"))
        self.profile["legacy_screen_coords"] = False
        self.log("Mapeamentos antigos convertidos. Se algum sair do lugar, capture de novo.")

    def _watch_window(self, now: float) -> None:
        if now < self._next_window_scan:
            return
        self._next_window_scan = now + WINDOW_SCAN_SECONDS
        if self.am is not None:
            if self.am.is_valid():
                return
            self.stop_all(announce=False)
            self._set_action_manager(None)
            self.log("A janela do jogo fechou.")
        hwnd = pick_game_window(self._list_windows(), self.profile["window_title"])
        if hwnd is not None:
            self.attach(hwnd, remember=False)

    def list_windows(self):
        return self._list_windows()

    # ---------- hotkeys ----------

    def on_key(self, name: str, shift: bool) -> None:
        if name == "esc":
            # stop_all espera threads terminarem, e isto roda no hook do teclado.
            threading.Thread(target=self.stop_all, daemon=True, name="parar").start()
        elif shift and name == "f1":
            self.set_module("macros", not self.macros_on)
        elif self.macros_on and name in self.profile["macros"]:
            if self.am is not None and self.am.is_foreground():
                self._enqueue(name)

    def _enqueue(self, key: str) -> None:
        try:
            self._actions.put_nowait(key)
        except queue.Full:
            logger.debug("Fila de ações cheia; ignorando %s", key)

    def _action_loop(self) -> None:
        while not self._shutdown.is_set():
            try:
                key = self._actions.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.macros.execute(key)
            except Exception:
                logger.exception("Erro ao executar a macro %s", key)

    def run_action(self, action: str) -> bool:
        """Executa uma macro salva, uma tecla no jogo ou, senão, fala o texto."""
        if self.am is None:
            return False
        if action in self.profile["macros"]:
            return self.macros.execute(action)
        if key_to_vk(action) is not None:
            return self.am.press_key(action)
        return self.am.send_text(action)

    # ---------- módulos ----------

    def stop_all(self, announce: bool = True) -> None:
        self.training_on = False
        self.macros_on = False
        self.alarm_on = False
        self.survival_on = False
        self.training_started_at = None
        self.machine.pause()
        self.fishing.stop()
        self.repeater.stop()
        self.rune_maker.stop()
        while not self._actions.empty():
            try:
                self._actions.get_nowait()
            except queue.Empty:
                break
        if announce:
            self.log("Tudo parado.")

    def _pause_afk_modules(self) -> None:
        """Alarme: para o que age sozinho. Cura e macros continuam."""
        self.training_on = False
        self.training_started_at = None
        self.machine.pause()
        self.fishing.stop()
        self.repeater.stop()
        self.rune_maker.stop()

    def set_module(self, name: str, on: bool) -> bool:
        handler = getattr(self, f"_set_{name}")
        if on and self.am is None:
            self.log("Abra o jogo ou escolha a janela em Ajustes.")
            return False
        result = handler(on)
        self.save()
        return result

    def _set_macros(self, on: bool) -> bool:
        if on and not self.profile["macros"]:
            self.log("Cadastre uma macro primeiro.")
            return False
        self.macros_on = on
        self.log("Macros ligadas." if on else "Macros desligadas.")
        return True

    def _set_training(self, on: bool) -> bool:
        if not on:
            self.training_on = False
            self.training_started_at = None
            self.machine.pause()
            return True
        if not self.profile["training"]["region"]:
            self.log("Selecione a região da battle list primeiro.")
            return False
        self.machine.set_mode(TrainingMode(self.profile["training"]["mode"]))
        self.machine.start()
        self.machine.train()
        self.training_on = True
        self.training_started_at = time.monotonic()
        self._next_battle = 0.0
        return True

    def _set_fishing(self, on: bool) -> bool:
        if not on:
            self.fishing.stop()
            return True
        if not self.fishing.start():
            self.log("Capture a vara e ao menos uma água primeiro.")
            return False
        return True

    def _set_repeater(self, on: bool) -> bool:
        if not on:
            self.repeater.stop()
            return True
        config = self.profile["repeater"]
        key = str(config["key"]).strip().lower()
        if key not in self.profile["macros"] and key_to_vk(key) is None:
            self.log(f"Tecla inválida no repetidor: {key!r}")
            return False
        try:
            return self.repeater.start(key, config["interval"], self.run_action)
        except ValueError as exc:
            self.log(str(exc))
            return False

    def _set_alarm(self, on: bool) -> bool:
        if on and not self.profile["training"]["region"]:
            self.log("O alarme lê a battle list: selecione a região em Treino.")
            return False
        self.alarm.reset()
        self.alarm_on = on
        self._next_battle = 0.0
        return True

    def _set_survival(self, on: bool) -> bool:
        self.survival.reset()
        self.survival_on = on
        return True

    def _set_rune_maker(self, on: bool) -> bool:
        if not on:
            self.rune_maker.stop()
            return True
        missing = self.rune_maker.missing()
        if missing:
            self.log(f"Rune maker: falta configurar {missing}.")
            return False
        return self.rune_maker.start()

    # ---------- visão ----------

    def _vision_loop(self) -> None:
        while not self._shutdown.wait(0.25):
            try:
                self.vision_tick(time.monotonic())
            except Exception:
                logger.exception("Erro no ciclo de visão")

    def _needs_bars(self) -> bool:
        survival = self.profile["survival"]
        has_bar = survival["hp_bar"] or survival["mana_bar"]
        return bool(has_bar and (self.survival_on or self.rune_maker.is_running))

    def vision_tick(self, now: float) -> None:
        self._watch_window(now)
        if self.am is None:
            return
        scan_battle = (self.training_on or self.alarm_on) and now >= self._next_battle
        scan_bars = self._needs_bars() and now >= self._next_bars
        if scan_battle or scan_bars:
            frame = self._capture_frame(self.am.hwnd)
            if scan_battle:
                self._next_battle = now + BATTLE_SCAN_SECONDS
                self._scan_battle(frame, now)
            if scan_bars:
                self._next_bars = now + BARS_SCAN_SECONDS
                survival = self.profile["survival"]
                self.hp = battle_vision.bar_percent(frame, survival["hp_bar"])
                self.mana = battle_vision.bar_percent(frame, survival["mana_bar"])
        if self.survival_on:
            self.survival.tick(now, self.hp, self.mana)

    def read_battle_list(self, frame):
        training = self.profile["training"]
        return battle_vision.analyze_battle_list(
            frame, training["region"], training["allowed_names"]
        )

    def _scan_battle(self, frame, now: float) -> None:
        if frame is None:
            return  # sem imagem não dá para concluir nada sobre a battle list
        snapshot = self.read_battle_list(frame)
        self.target_count = len(snapshot.rows)

        if self.alarm_on:
            message = self.alarm.evaluate(snapshot, now, bool(self.profile["training"]["allowed_names"]))
            if message:
                self._raise_alarm(message)

        if self.training_on:
            pos, reason = self.planner.plan(snapshot, now)
            if pos is not None:
                self.am.left_click(pos)
                logger.info(reason)

    def _raise_alarm(self, message: str) -> None:
        config = self.profile["alarm"]
        if config["pause_modules"]:
            self._pause_afk_modules()
        self.log(f"ALARME: {message}")
        self.events.put(("alarm", message))
        if config["sound"]:
            threading.Thread(target=beep, daemon=True, name="alarme").start()

    # ---------- capturas ----------

    def _begin_capture(self, prompt: str, count: int, on_done) -> bool:
        if self.am is None:
            self.log("Abra o jogo ou escolha a janela em Ajustes.")
            return False
        self.cancel_capture()
        self._emit_prompt(prompt)

        def on_point(captured):
            if count > 1:
                self._emit_prompt(f"{prompt} ({captured}/{count})")

        def finished(points):
            self._click_capture = None
            self._emit_prompt(None)
            if points:
                on_done(points)
                self.save()
            else:
                self.log("Captura cancelada: nenhum clique no jogo.")

        self._click_capture = ClickCapture(self.am, count, CAPTURE_TIMEOUT_SECONDS, on_point, finished)
        self._click_capture.start()
        return True

    def cancel_capture(self) -> None:
        if self._click_capture is not None:
            self._click_capture.cancel()

    def capture_macro(self, key: str, mode: str) -> bool:
        key = str(key).strip().lower()
        if not key:
            self.log("Informe a hotkey antes de capturar.")
            return False
        if len(key) == 1:
            self.log(f"Atenção: '{key}' também dispara enquanto você digita no chat. Prefira teclas F.")

        if mode != "drag":
            def save_rune(points):
                self.profile["macros"][key] = {"mode": mode, "pos": points[0], "end": None}
                self.log(f"Macro '{key}' salva.")
            return self._begin_capture(f"Clique na runa de {key} no jogo", 1, save_rune)

        def save_drag(points):
            if len(points) < 2:
                self.log("Puxar item precisa de dois cliques: origem e destino.")
                return
            self.profile["macros"][key] = {"mode": "drag", "pos": points[0], "end": points[1]}
            self.log(f"Macro '{key}' salva.")
        return self._begin_capture("Clique na origem e depois no destino", 2, save_drag)

    def remove_macro(self, key: str) -> None:
        self.profile["macros"].pop(key, None)
        self.save()

    def capture_player(self) -> bool:
        def done(points):
            self.profile["player_position"] = points[0]
            self.log("Posição do player salva.")
        return self._begin_capture("Clique no seu personagem", 1, done)

    def capture_rod(self) -> bool:
        def done(points):
            self.profile["fishing"]["rod"] = points[0]
            self.log("Vara salva.")
        return self._begin_capture("Clique na vara de pesca", 1, done)

    def capture_waters(self, count: int = 5) -> bool:
        def done(points):
            self.profile["fishing"]["waters"] = points
            self.log(f"{len(points)} água(s) salva(s).")
        return self._begin_capture("Clique nas águas", count, done)

    def reset_fishing(self) -> None:
        self.fishing.stop()
        self.profile["fishing"]["rod"] = None
        self.profile["fishing"]["waters"] = []
        self.save()

    def capture_food(self) -> bool:
        def done(points):
            self.profile["survival"]["eat"]["pos"] = points[0]
            self.log("Comida salva.")
        return self._begin_capture("Clique na comida", 1, done)

    def capture_rune_maker(self, field: str, label: str) -> bool:
        def done(points):
            self.profile["rune_maker"][field] = points[0]
            self.log(f"Rune maker: {label} salvo.")
        return self._begin_capture(f"Clique em: {label}", 1, done)

    def set_region_from_screen(self, target: str, screen_rect) -> bool:
        """Salva um retângulo da tela, relativo à janela do jogo."""
        if self.am is None:
            self.log("Abra o jogo ou escolha a janela em Ajustes.")
            return False
        left, top, width, height = screen_rect
        client_left, client_top = self.am.screen_to_client((left, top))
        rect = [client_left, client_top, width, height]
        if target == "battle":
            if width < 80 or height < 60:
                self.log("Região muito pequena para a battle list.")
                return False
            self.profile["training"]["region"] = rect
        else:
            self.profile["survival"][target] = rect
        self.save()
        self.log("Região salva.")
        return True

    def test_capture(self):
        """Lê a battle list agora. Devolve (frame recortado, snapshot) para a prévia."""
        region = self.profile["training"]["region"]
        if self.am is None or not region:
            self.log("Selecione a janela e a região da battle list primeiro.")
            return None, None
        frame = self._capture_frame(self.am.hwnd)
        if frame is None:
            self.log("Sem imagem: o jogo está minimizado?")
            return None, None
        snapshot = self.read_battle_list(frame)
        selected = snapshot.selected_index
        self.log(
            f"{len(snapshot.rows)} alvo(s) lido(s); "
            f"selecionado: {'nenhum' if selected is None else f'#{selected}'}."
        )
        return battle_vision.crop(frame, region), snapshot

    def learn_visible_names(self) -> None:
        """Marca os nomes visíveis agora na battle list como permitidos."""
        region = self.profile["training"]["region"]
        if self.am is None or not region:
            self.log("Selecione a janela e a região da battle list primeiro.")
            return
        frame = self._capture_frame(self.am.hwnd)
        allowed = self.profile["training"]["allowed_names"]
        added = 0
        for row in battle_vision.analyze_battle_list(frame, region).rows:
            known = any(battle_vision.signatures_match(row.signature, name) for name in allowed)
            if row.signature and not known:
                allowed.append(row.signature)
                added += 1
        self.save()
        self.log(f"{added} nome(s) novo(s); {len(allowed)} permitido(s) no total.")

    def clear_allowed_names(self) -> None:
        self.profile["training"]["allowed_names"] = []
        self.save()
        self.log("Lista de nomes permitidos limpa.")

    # ---------- status para a UI ----------

    def status(self) -> dict:
        profile = self.profile
        training_detail = "Summon" if profile["training"]["mode"] == "summon" else "Normal"
        if self.training_started_at is not None:
            minutes = int((time.monotonic() - self.training_started_at) // 60)
            training_detail += f" · {minutes // 60:02d}:{minutes % 60:02d} · {self.target_count} alvo(s)"
        elif not profile["training"]["region"]:
            training_detail = "Falta a região da battle list"

        fishing_on = self.fishing.status == Status.Active
        if fishing_on:
            fishing_detail = f"{self.fishing.attempts} tentativas"
        else:
            fishing_detail = f"{len(profile['fishing']['waters'])} água(s)"

        rules = sum(1 for rule in profile["survival"]["rules"] if rule["enabled"])
        vitals = []
        if self.hp is not None:
            vitals.append(f"HP {self.hp:.0f}%")
        if self.mana is not None:
            vitals.append(f"Mana {self.mana:.0f}%")
        survival_detail = " · ".join(vitals) or f"{rules} regra(s) ativa(s)"

        allowed = len(profile["training"]["allowed_names"])
        return {
            "connected": self.am is not None,
            "title": self.am.title() if self.am else "",
            "training": (self.training_on, training_detail),
            "fishing": (fishing_on, fishing_detail),
            "macros": (self.macros_on, f"{len(profile['macros'])} hotkey(s)"),
            "repeater": (self.repeater.is_running,
                         f"{profile['repeater']['key']} · {profile['repeater']['interval']} s"),
            "alarm": (self.alarm_on, f"{allowed} nome(s) permitido(s)" if allowed else "Avisa se a lista crescer"),
            "survival": (self.survival_on, survival_detail),
            "rune_maker": (self.rune_maker.is_running, f"{self.rune_maker.casts} runa(s) feita(s)"),
        }

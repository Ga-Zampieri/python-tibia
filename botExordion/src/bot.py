"""Controlador do bot: toda a lógica, sem nada de interface.

A UI lê `status()`, chama os métodos públicos e consome `events`. Nenhuma thread
daqui toca em widget.
"""
from __future__ import annotations

import itertools
import json
import logging
import queue
import threading
import time
from pathlib import Path

from . import battle_vision, loot
from .action_manager import PRIORITIES, ActionManager, key_to_vk, priority
from .alarm import AlarmMonitor
from .auto_hotkey import AutoHotkey
from .capture import capture_client, grab_visible_areas
from .click_capture import ClickCapture
from .fishing import Pesca
from .hotkey_service import HotkeyService, combo_name
from .macros import MacroRunner
from .rune_maker import RuneMaker
from .settings import DEFAULT_PROFILE, PROFILE_FORMAT, ProfileStore, conform, merge_defaults
from .status import Status
from .survival import Survival
from .training import AttackPlanner, HealPlanner, NormalOrder, TrainingMode, TrainingStateMachine
from .window_handler import getWindows, pick_game_window

logger = logging.getLogger(__name__)

BATTLE_SCAN_SECONDS = 1.5
BARS_SCAN_SECONDS = 0.5
WINDOW_SCAN_SECONDS = 2.0
CAPTURE_TIMEOUT_SECONDS = 30
INPUT_TEST_WAIT = 15
SLOT_RADIUS = 12

MODULES = (
    ("training", "Treino"),
    ("fishing", "Pesca"),
    ("macros", "Macros"),
    ("loot", "Loot"),
    ("repeater", "Repetidor"),
    ("alarm", "Alarme"),
    ("survival", "Sobrevivência"),
    ("rune_maker", "Rune Maker"),
)
MODULE_TITLES = dict(MODULES)


def beep() -> None:
    import winsound
    for _ in range(3):
        winsound.Beep(1200, 250)


class BotController:
    def __init__(self, store=None, capture=capture_client, list_windows=getWindows, grab=grab_visible_areas):
        self.store = store or ProfileStore()
        self._capture_frame = capture
        self._grab = grab
        self._fast_capture = None  # None: ainda não conferida neste jogo
        # Janelas do próprio bot (a UI preenche): a captura rápida não pode lê-las.
        self.covering_windows = lambda: []
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
        self._hotkey_target = None
        self._toggle_lock = threading.Lock()

        self._actions = queue.PriorityQueue(maxsize=16)
        self._tickets = itertools.count()
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
        if self._another_instance():
            message = ("Outro Exordion já está aberto. Os dois respondem às mesmas hotkeys e, no mesmo "
                       "perfil, um apaga o que o outro salva.")
            self.log(message)
            self.events.put(("warning", message))
        self._hotkeys.start()
        threading.Thread(target=self._action_loop, daemon=True, name="acoes").start()
        threading.Thread(target=self._vision_loop, daemon=True, name="visao").start()

    def _another_instance(self) -> bool:
        try:
            import win32api
            import win32event
            import winerror
            # O handle fica guardado: o nome existe enquanto este bot estiver aberto.
            self._instance_mutex = win32event.CreateMutex(None, False, "Local\\Exordion")
            return win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS
        except Exception:
            logger.exception("Não deu para conferir outras cópias abertas")
            return False

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
        try:
            self.store.save(self.profile_name, self.profile)
        except OSError as exc:
            logger.exception("Falha ao salvar o perfil")
            self.log(f"Não consegui salvar o perfil agora ({exc.strerror or exc}). Salvo na próxima mudança.")

    # ---------- perfis ----------

    def _use_profile(self, name: str, profile: dict) -> None:
        self.profile_name = name
        self.profile = profile
        self.macros = MacroRunner(profile, self.log)
        self.fishing = Pesca(profile["fishing"])
        self.machine = TrainingStateMachine(mode=TrainingMode(profile["training"]["mode"]))
        self.planner = AttackPlanner(self.machine)
        self.healer = HealPlanner()
        self.survival = Survival(profile["survival"], self._queue_heal)
        self.rune_maker = RuneMaker(profile["rune_maker"], lambda: self.mana, self.log,
                                    get_frame=lambda: self._game_frame([self._hand_area()]), alert=self._notify)
        self.looter = loot.Looter(profile, self.log, alert=self._notify,
                                  get_frame=lambda: self._game_frame([loot.capture_area(self.profile["loot"]["grid"])]))
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

    def rename_profile(self, name: str) -> bool:
        new = self.store.clean_name(name)
        if not new or new == self.profile_name:
            return False
        if self.store.exists(new) and new.casefold() != self.profile_name.casefold():
            self.log(f"Já existe um perfil chamado {new}.")
            return False
        self.save()
        try:
            self.store.rename(self.profile_name, new)
        except OSError as exc:
            self.log(f"Não foi possível renomear o perfil ({exc}).")
            return False
        old, self.profile_name = self.profile_name, new
        self.store.remember_last(new)
        self.log(f"Perfil {old} agora se chama {new}.")
        return True

    def export_profile(self, path) -> None:
        self.save()
        data = {"format": PROFILE_FORMAT, "version": 1, "name": self.profile_name, "profile": self.profile}
        try:
            Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            self.log(f"Não foi possível salvar o perfil ({exc}).")
            return
        self.log(f"Perfil {self.profile_name} exportado.")

    def import_profile(self, path) -> bool:
        """Vira um perfil novo, sem nunca sobrescrever um que já existe."""
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if not isinstance(data, dict) or data.get("format") != PROFILE_FORMAT or not isinstance(data.get("profile"), dict):
            self.log("Esse arquivo não é um perfil do Exordion.")
            return False
        profile = merge_defaults(DEFAULT_PROFILE, conform(DEFAULT_PROFILE, data["profile"]))
        config = profile["loot"]
        sprites = {kind: config[kind] for kind in ("items", "bags", "routes")}
        config.update(items=[], bags=[], routes={})
        if loot.import_list(config, {"format": loot.LIST_FORMAT, **sprites}) is None:
            self.log("A lista de loot do perfil estava estragada e ficou de fora.")
        name = self.store.unique_name(data.get("name") or "Importado")
        self.store.save(name, profile)
        self.switch_profile(name)
        self.log(f"Perfil {name} importado.")
        return True

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
        self._fast_capture = None
        if am is not None:
            am.configure(self.profile["input"])
        for module in (self.macros, self.fishing, self.survival, self.rune_maker, self.looter):
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

    def on_key(self, name: str, mods=(), repeat: bool = False) -> None:
        """Roda no hook do teclado: o que pode demorar vai para `_in_background`."""
        if name == "esc":
            self._cancel_hotkey_capture()
            self._in_background(self.stop_all)
            return
        if self._hotkey_target is not None:
            if not repeat:
                target, self._hotkey_target = self._hotkey_target, None
                self._in_background(self._assign_hotkey, target, name, mods)
            return
        module = self._module_for(combo_name(name, mods))
        if module is not None:
            # Segurar a tecla não pode ficar ligando e desligando.
            if not repeat and self._hotkey_allowed(module):
                self._in_background(self._toggle_module, module)
        elif self.macros_on and name in self.profile["macros"] and self._game_in_front():
            self._enqueue(name)

    def _hotkey_allowed(self, module: str) -> bool:
        if module != "loot":
            return True
        # Age na hora, como uma macro. Um toque a mais não pode cancelar a coleta.
        return self._game_in_front() and not self.looter.is_running

    def _game_in_front(self) -> bool:
        return self.am is not None and self.am.is_foreground()

    def _in_background(self, target, *args) -> None:
        threading.Thread(target=target, args=args, daemon=True, name="atalho").start()

    def _module_for(self, combo: str):
        for module, hotkey in self.profile["module_hotkeys"].items():
            if hotkey == combo:
                return module
        return None

    def _toggle_module(self, name: str) -> None:
        with self._toggle_lock:
            self.set_module(name, not self.status()[name][0])

    def capture_module_hotkey(self, module: str) -> None:
        """A próxima tecla apertada, em qualquer janela, vira o atalho do módulo."""
        self.cancel_capture()
        self._hotkey_target = module
        self._emit_prompt(f"Aperte o atalho de {MODULE_TITLES[module]}")

    def _cancel_hotkey_capture(self) -> None:
        if self._hotkey_target is not None:
            self._hotkey_target = None
            self._emit_prompt(None)

    def _assign_hotkey(self, module: str, name: str, mods) -> None:
        self._emit_prompt(None)
        combo = combo_name(name, mods)
        owner = self._module_for(combo)
        if owner not in (None, module):
            self.log(f"{combo.upper()} já é o atalho de {MODULE_TITLES[owner]}.")
            return
        if combo in self.profile["macros"]:
            self.log(f"{combo.upper()} já é uma macro. Escolha outro atalho.")
            return
        if len(name) == 1 and not {"ctrl", "alt"} & set(mods):
            self.log(f"Atenção: '{combo}' também dispara enquanto você digita, em qualquer janela.")
        self.profile["module_hotkeys"][module] = combo
        self.save()
        self.log(f"{MODULE_TITLES[module]}: atalho {combo.upper()}.")
        self.events.put(("hotkeys", None))

    def clear_module_hotkey(self, module: str) -> None:
        self.profile["module_hotkeys"][module] = ""
        self.save()
        self.events.put(("hotkeys", None))

    def queue_action(self, level: str, label: str, action) -> bool:
        """Põe na fila única de ações: a de maior prioridade sai primeiro."""
        try:
            self._actions.put_nowait((PRIORITIES[level], next(self._tickets), level, label, action))
            return True
        except queue.Full:
            logger.debug("Fila de ações cheia; ignorando %s", label)
            return False

    def _enqueue(self, key: str) -> None:
        self.queue_action("macro", key, lambda: self.macros.execute(key))

    def _queue_heal(self, action: str) -> bool:
        """Regras da Sobrevivência: na frente de tudo, e sem travar a leitura da tela."""
        return self.queue_action("heal", action, lambda: self.run_action(action))

    def run_next_action(self, timeout: float = 0.5) -> bool:
        try:
            _, _, level, label, action = self._actions.get(timeout=timeout)
        except queue.Empty:
            return False
        try:
            with priority(level):
                action()
        except Exception:
            logger.exception("Erro ao executar %s", label)
        return True

    def _action_loop(self) -> None:
        while not self._shutdown.is_set():
            self.run_next_action()

    def _repeat(self, key: str) -> bool:
        with priority("repeater"):
            return self.run_action(key)

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
        self.looter.stop()
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
        if result:
            self.log(f"{MODULE_TITLES[name]}: {'ligado' if on else 'desligado'}.")
        return result

    def _set_macros(self, on: bool) -> bool:
        if on and not self.profile["macros"]:
            self.log("Cadastre uma macro primeiro.")
            return False
        self.macros_on = on
        return True

    def _set_loot(self, on: bool) -> bool:
        if not on:
            self.looter.stop()
            return True
        missing = self.looter.missing()
        if missing:
            self.log(f"Loot: falta configurar {missing}.")
            return False
        return self.looter.start()

    def _set_training(self, on: bool) -> bool:
        if not on:
            self.training_on = False
            self.training_started_at = None
            self.machine.pause()
            return True
        if not self.profile["training"]["region"]:
            self.log("Selecione a região da battle list primeiro.")
            return False
        self.apply_training_mode()
        self.healer.reset()
        self.machine.start()
        self.machine.train()
        self.training_on = True
        self.training_started_at = time.monotonic()
        self._next_battle = 0.0
        return True

    def apply_training_mode(self) -> None:
        """Leva o tipo de criatura e a ordem do Normal do perfil para o treino."""
        training = self.profile["training"]
        self.machine.set_mode(TrainingMode(training["mode"]), NormalOrder(training["normal_order"]))

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
            return self.repeater.start(key, config["interval"], self._repeat)
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
            survival = self.profile["survival"]
            areas = []
            if scan_battle:
                areas.append(self.profile["training"]["region"])
            if scan_bars:
                areas += [survival["hp_bar"], survival["mana_bar"]]
            frame = self._game_frame(areas)
            if scan_battle:
                self._next_battle = now + BATTLE_SCAN_SECONDS
                self._scan_battle(frame, now)
            if scan_bars:
                self._next_bars = now + BARS_SCAN_SECONDS
                self.hp = battle_vision.bar_percent(frame, survival["hp_bar"])
                self.mana = battle_vision.bar_percent(frame, survival["mana_bar"])
        if self.survival_on:
            self.survival.tick(now, self.hp, self.mana)

    def read_battle_list(self, frame):
        training = self.profile["training"]
        return battle_vision.analyze_battle_list(
            frame, training["region"], training["allowed_names"], training["ignored_names"]
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
            elif self.machine.mode == TrainingMode.NORMAL_CREATURES:
                self._heal_target(snapshot, now)

    def _heal_target(self, snapshot, now: float) -> None:
        heal = self.profile["training"]["heal"]
        pos, reason = self.healer.plan(snapshot, now, heal)
        if pos is not None:
            logger.info(reason)
            self.queue_action("macro", "cura do alvo", lambda: self.macros.use_rune_on(heal["rune"], pos, "cura"))

    def _hand_area(self):
        hand = self.profile["rune_maker"]["hand"]
        return (hand[0] - SLOT_RADIUS, hand[1] - SLOT_RADIUS, SLOT_RADIUS * 2, SLOT_RADIUS * 2) if hand else None

    def _game_frame(self, areas=None):
        """Imagem do jogo. Com `areas`, tenta ler só esses pedaços da tela (1 a 2 ms
        cada, contra uns 50 ms da captura completa). Fora deles o frame é preto."""
        am = self.am
        if am is None:
            return None
        areas = [area for area in areas or () if area]
        if areas and self._fast_capture is not False:
            fast = self._grab(am.hwnd, areas, self.covering_windows())
            if fast is not None:
                if self._fast_capture:
                    return fast
                return self._check_fast_capture(am, areas, fast)
        return self._capture_frame(am.hwnd)

    def _check_fast_capture(self, am, areas, fast):
        """Na primeira vez, compara com a captura completa. Com a tela em escala
        diferente de 100%, por exemplo, a tela mostra o jogo esticado e os desenhos
        aprendidos deixariam de bater: aí a captura rápida fica desligada."""
        full = self._capture_frame(am.hwnd)
        if full is None:
            return None
        self._fast_capture = all(
            battle_vision.same_image(battle_vision.crop(full, area), battle_vision.crop(fast, area))
            for area in areas)
        logger.info("Captura rápida %s.", "ligada" if self._fast_capture else "desligada: a tela difere do jogo")
        return full

    # ---------- teste de input ----------

    def test_input(self) -> bool:
        """Descobre se o arraste por mensagem funciona com o jogo na frente."""
        if self.am is None or not self.profile["loot"]["grid"]:
            self.log("Teste de input: conecte o jogo e selecione os slots do loot primeiro.")
            return False
        self._in_background(self._run_input_test)
        return True

    def _run_input_test(self) -> None:
        am = self.am
        self.log("Teste de input: deixe nos slots do loot uma mochila com um item sem valor e um slot vazio, "
                 f"e clique no jogo ({INPUT_TEST_WAIT} s).")
        deadline = time.monotonic() + INPUT_TEST_WAIT
        while not am.is_foreground():
            if time.monotonic() > deadline or self._shutdown.is_set():
                self.log("Teste de input: o jogo não veio para frente. Nada foi testado.")
                return
            time.sleep(0.2)
        time.sleep(0.5)  # o clique que trouxe o jogo para frente termina
        with priority("macro"):
            by_message = self._test_drag(am, messages=True)
            if by_message is None:
                return
            by_cursor = by_message or self._test_drag(am, messages=False)
        settings = self.profile["input"]
        if by_message:
            settings["mode"] = "message"
            self.log("Teste de input: o arraste por mensagem funcionou com o jogo na frente. Passei para Só mensagem.")
        elif by_cursor:
            settings["mode"] = "auto"
            self.log("Teste de input: por mensagem o item não se mexeu com o jogo na frente; pelo cursor, sim. "
                     "Fica no Automático.")
        else:
            self.log("Teste de input: o item não se mexeu de nenhum jeito. Ele é movível e a mochila tem espaço?")
        self.save()
        self.events.put(("input", None))

    def _test_drag(self, am, messages: bool):
        """True se o item andou, False se não, None se não deu para testar."""
        grid = self.profile["loot"]["grid"]
        frame = self._game_frame()
        view = loot.read_view(frame, grid) if frame is not None else []
        item = next((slot for slot in view if not loot.is_empty(slot.pixels)), None)
        empty = next((slot for slot in view if loot.is_empty(slot.pixels)), None)
        if item is None or empty is None:
            self.log("Teste de input: preciso de um item e de um slot vazio nos slots do loot.")
            return None
        start = (item.left + loot.SLOT // 2, item.top + item.pixels.shape[0] // 2)
        end = (empty.left + loot.SLOT // 2, empty.top + empty.pixels.shape[0] // 2)
        with am.guarded() as held:
            if not held:
                self.log("Teste de input: não foi possível segurar o mouse.")
                return None
            if messages:
                am.drag(start, end, quick=True)
            else:
                am.drag_with_cursor(start, end, quick=True)
        deadline = time.monotonic() + float(self.profile["input"]["server_wait"])
        while time.monotonic() < deadline:
            time.sleep(0.05)
            after = self._game_frame()
            if after is not None and loot.view_changed(view, loot.read_view(after, grid)):
                return True
        return False

    def _raise_alarm(self, message: str) -> None:
        if self.profile["alarm"]["pause_modules"]:
            self._pause_afk_modules()
        self._notify(message)

    def _notify(self, message: str) -> None:
        """Avisa com faixa e som, mesmo com o módulo Alarme desligado."""
        self.log(f"ALARME: {message}")
        self.events.put(("alarm", message))
        if self.profile["alarm"]["sound"]:
            threading.Thread(target=beep, daemon=True, name="alarme").start()

    # ---------- capturas ----------

    def _begin_capture(self, prompt: str, count: int, on_done) -> bool:
        if self.am is None:
            self.log("Abra o jogo ou escolha a janela em Ajustes.")
            return False
        self.cancel_capture()
        self._emit_prompt(prompt)
        capture = None

        def on_point(captured):
            if count > 1:
                self._emit_prompt(f"{prompt} ({captured}/{count})")

        def finished(points):
            if self._click_capture is not capture:
                return  # outra captura tomou o lugar: a faixa e o Cancelar já são dela
            self._click_capture = None
            self._emit_prompt(None)
            if points:
                on_done(points)
                self.save()
            else:
                self.log("Captura cancelada: nenhum clique no jogo.")

        capture = ClickCapture(self.am, count, CAPTURE_TIMEOUT_SECONDS, on_point, finished)
        self._click_capture = capture
        capture.start()
        return True

    def cancel_capture(self) -> None:
        self._cancel_hotkey_capture()
        if self._click_capture is not None:
            self._click_capture.cancel()

    def capture_macro(self, key: str, mode: str) -> bool:
        key = str(key).strip().lower()
        if not key:
            self.log("Informe a hotkey antes de capturar.")
            return False
        owner = self._module_for(key)
        if owner is not None:
            self.log(f"{key.upper()} já é o atalho de {MODULE_TITLES[owner]}.")
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

    def capture_loot_destination(self, index: int = 0) -> bool:
        """Captura a BP desse número; um número além da última cria uma nova."""
        def done(points):
            config = self.profile["loot"]
            if index == 0:
                config["destination"] = points[0]
            elif index <= len(config["extra_destinations"]):
                config["extra_destinations"][index - 1] = points[0]
            else:
                config["extra_destinations"].append(points[0])
            self.log(f"Loot: BP {index + 1} salva.")
            self.events.put(("loot", None))
        return self._begin_capture(f"Clique na mochila da BP {index + 1}", 1, done)

    def remove_loot_destination(self, index: int) -> None:
        loot.remove_destination(self.profile["loot"], index)
        self.save()
        self.log("Loot: BP removida. Os itens dela voltaram para a BP 1.")
        self.events.put(("loot", None))

    def route_loot(self, item: int, destination: int) -> None:
        config = self.profile["loot"]
        loot.set_route(config, config["items"][item], destination)
        self.save()
        self.events.put(("loot", None))

    def capture_loot_close(self) -> bool:
        def done(points):
            self.profile["loot"]["close"] = points[0]
            self.log("X do loot salvo.")
        return self._begin_capture("Clique no X da janela do loot", 1, done)

    def clear_loot_close(self) -> None:
        self.profile["loot"]["close"] = None
        self.save()
        self.log("O loot não vai mais fechar a janela.")

    def _set_loot_grid(self, rect) -> bool:
        frame = self._game_frame()
        grid = loot.find_grid(frame, rect) if frame is not None else None
        if grid is None:
            self.log("Não achei os slots aí. Selecione só a área dos itens.")
            return False
        self.profile["loot"]["grid"] = grid
        self.save()
        self.log(f"Loot: {grid[2]} x {grid[3]} slots. Confira em Testar leitura.")
        return True

    def learn_loot(self, kind: str) -> None:
        """Aprende o que está visível agora nos slots: `items` ou `bags`."""
        config = self.profile["loot"]
        frame = self._game_frame()
        if frame is None or not config["grid"]:
            self.log("Selecione os slots do loot com o jogo aberto.")
            return
        known = config["items"] + config["bags"]
        added = 0
        for slot in loot.read_slots(frame, config["grid"]):
            if not loot.is_empty(slot.pixels) and not loot.is_known(slot.pixels, known):
                sprite = loot.encode_sprite(slot.pixels)
                config[kind].append(sprite)
                known.append(sprite)
                added += 1
        self.save()
        self.log(f"Loot: {added} novo(s), {len(config[kind])} no total.")
        self.events.put(("loot", None))

    def remove_loot(self, kind: str, index: int) -> None:
        config = self.profile["loot"]
        config["routes"].pop(config[kind].pop(index), None)
        self.save()
        self.events.put(("loot", None))

    def export_loot(self, path) -> None:
        config = self.profile["loot"]
        if not config["items"] and not config["bags"]:
            self.log("Loot: nada aprendido para exportar.")
            return
        try:
            Path(path).write_text(json.dumps(loot.export_list(config)), encoding="utf-8")
        except OSError as exc:
            self.log(f"Loot: não foi possível salvar a lista ({exc}).")
            return
        self.log(f"Loot: lista exportada, {len(config['items'])} item(ns) e {len(config['bags'])} bag(s).")

    def import_loot(self, path) -> None:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        added = loot.import_list(self.profile["loot"], data)
        if added is None:
            self.log("Loot: esse arquivo não é uma lista de loot válida.")
            return
        self.save()
        self.log(f"Loot: {added} novo(s) importado(s).")
        self.events.put(("loot", None))

    def test_loot(self):
        """Lê os slots agora. Devolve (recorte, [(x, y, tipo)]) para a prévia."""
        grid = self.profile["loot"]["grid"]
        frame = self._game_frame()
        if frame is None or not grid:
            self.log("Selecione os slots do loot com o jogo aberto.")
            return None, None
        left, top, columns, rows = grid
        size = (loot.PITCH * (columns - 1) + loot.SLOT, loot.PITCH * (rows - 1) + loot.SLOT)
        slots = [(slot.left - left, slot.top - top, self.looter.classify(slot.pixels))
                 for slot in loot.read_slots(frame, grid)]
        kinds = [kind for _, _, kind in slots]
        self.log(f"Loot: {kinds.count('item')} item(ns), {kinds.count('bag')} bag(s), "
                 f"{kinds.count('other')} ignorado(s).")
        return battle_vision.crop(frame, (left, top, *size)), slots

    def set_region_from_screen(self, target: str, screen_rect) -> bool:
        """Salva um retângulo da tela, relativo à janela do jogo."""
        if self.am is None:
            self.log("Abra o jogo ou escolha a janela em Ajustes.")
            return False
        left, top, width, height = screen_rect
        client_left, client_top = self.am.screen_to_client((left, top))
        rect = [client_left, client_top, width, height]
        if target == "loot":
            return self._set_loot_grid(rect)
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
        """Salva como "atacar" os nomes visíveis agora que ainda não estão salvos."""
        region = self.profile["training"]["region"]
        if self.am is None or not region:
            self.log("Selecione a janela e a região da battle list primeiro.")
            return
        frame = self._capture_frame(self.am.hwnd)
        training = self.profile["training"]
        allowed = training["allowed_names"]
        added = 0
        for row in battle_vision.analyze_battle_list(frame, region).rows:
            saved = allowed + training["ignored_names"]
            known = any(battle_vision.signatures_match(row.signature, name) for name in saved)
            if row.signature and not known:
                allowed.append(row.signature)
                added += 1
        self._names_changed(f"{added} nome(s) novo(s); {len(allowed)} para atacar no total.")

    def clear_allowed_names(self) -> None:
        self.profile["training"]["allowed_names"] = []
        self.profile["training"]["ignored_names"] = []
        self._names_changed("Lista de nomes limpa.")

    def set_name_ignored(self, kind: str, index: int, ignored: bool) -> None:
        """Move um nome salvo entre "atacar" (allowed) e "ignorar" (ignored)."""
        training = self.profile["training"]
        source = training[f"{kind}_names"]
        target = training["ignored_names" if ignored else "allowed_names"]
        if not 0 <= index < len(source) or source is target:
            return
        target.append(source.pop(index))
        self._names_changed("Nome marcado para ignorar." if ignored else "Nome marcado para atacar.")

    def remove_name(self, kind: str, index: int) -> None:
        names = self.profile["training"][f"{kind}_names"]
        if 0 <= index < len(names):
            del names[index]
            self._names_changed("Nome removido.")

    def _names_changed(self, message: str) -> None:
        self.save()
        self.events.put(("names", None))
        self.log(message)

    def capture_heal_rune(self) -> bool:
        def done(points):
            self.profile["training"]["heal"]["rune"] = points[0]
            self.events.put(("names", None))
            self.log("Runa de cura salva.")
        return self._begin_capture("Clique na runa de cura", 1, done)

    # ---------- painel sobre o jogo ----------

    def overlay_state(self, status=None):
        """Onde e o que o painel mostra, ou None para escondê-lo.

        Só com o jogo na frente: por cima de outro programa o painel atrapalharia."""
        config = self.profile["overlay"]
        am = self.am
        if not config["enabled"] or am is None or not am.is_foreground() or am.is_minimized():
            return None
        status = status or self.status()
        hotkeys = self.profile["module_hotkeys"]
        rows = [(title, hotkeys[name].upper(), status[name][0]) for name, title in MODULES
                if status[name][0] or hotkeys[name]]
        if not rows:
            return None
        return {"client": am.client_rect_on_screen(), "corner": config["corner"], "rows": rows}

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
        missing = self.looter.missing()
        loot_detail = f"Falta {missing}" if missing else f"{len(profile['loot']['items'])} item(ns) aprendido(s)"
        return {
            "connected": self.am is not None,
            "title": self.am.title() if self.am else "",
            "training": (self.training_on, training_detail),
            "fishing": (fishing_on, fishing_detail),
            "macros": (self.macros_on, f"{len(profile['macros'])} hotkey(s)"),
            "loot": (self.looter.is_running, loot_detail),
            "repeater": (self.repeater.is_running,
                         f"{profile['repeater']['key']} · {profile['repeater']['interval']} s"),
            "alarm": (self.alarm_on, f"{allowed} nome(s) permitido(s)" if allowed else "Avisa se a lista crescer"),
            "survival": (self.survival_on, survival_detail),
            "rune_maker": (self.rune_maker.is_running, f"{self.rune_maker.casts} runa(s) feita(s)"),
        }

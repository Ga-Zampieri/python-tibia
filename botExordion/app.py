import argparse
import contextlib
import io
import logging
import os
import threading
import time
import tkinter as tk
from tkinter import BooleanVar, StringVar, ttk

try:
    from PIL import ImageGrab, ImageTk, Image, ImageOps
except Exception:  # pragma: no cover
    ImageGrab = None
    ImageTk = None
    Image = None
    ImageOps = None

try:
    import numpy as np
except Exception:
    np = None

try:
    import mss as _mss_module
except Exception:
    _mss_module = None

from src.battle_list_selector import (
    BattleListRegion,
    BattleListRegionValidator,
    BattleListRow,
    BattleListSnapshot,
    SelectorState,
)
from src.training import TrainingStateMachine, TrainingMode

logging.getLogger('pytesseract').setLevel(logging.CRITICAL)


# ============================================================
# Multi-monitor / DPI helpers
# ============================================================

def _enable_dpi_awareness():
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    except Exception:
        pass


def _get_virtual_screen_bounds():
    """(left, top, width, height) cobrindo TODOS os monitores."""
    try:
        import ctypes
        u = ctypes.windll.user32
        return (
            u.GetSystemMetrics(76),  # SM_XVIRTUALSCREEN
            u.GetSystemMetrics(77),  # SM_YVIRTUALSCREEN
            u.GetSystemMetrics(78),  # SM_CXVIRTUALSCREEN
            u.GetSystemMetrics(79),  # SM_CYVIRTUALSCREEN
        )
    except Exception:
        return 0, 0, 1920, 1080


_mss_instance = None
_mss_lock = threading.Lock()


def _grab_screen(bbox=None):
    """Captura qualquer monitor. bbox=(l, t, r, b) em coords do desktop virtual."""
    global _mss_instance

    if _mss_module is not None:
        try:
            with _mss_lock:
                if _mss_instance is None:
                    _mss_instance = _mss_module.mss()
                if bbox is None:
                    vleft, vtop, vwidth, vheight = _get_virtual_screen_bounds()
                    monitor = {"left": vleft, "top": vtop,
                               "width": max(1, vwidth), "height": max(1, vheight)}
                else:
                    left, top, right, bottom = [int(v) for v in bbox]
                    monitor = {"left": left, "top": top,
                               "width": max(1, right - left),
                               "height": max(1, bottom - top)}
                shot = _mss_instance.grab(monitor)
            if Image is None:
                return None
            return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        except Exception:
            pass

    if ImageGrab is None:
        return None
    try:
        try:
            return ImageGrab.grab(bbox=bbox, all_screens=True)
        except TypeError:
            return ImageGrab.grab(bbox=bbox)
    except Exception:
        return None


# ============================================================
# Controllers / estado global
# ============================================================

def _load_action_manager(hwnd):
    from src.action_manager import ActionManager
    return ActionManager(hwnd)


def _load_runa(action_manager):
    from src.macro_rune import Runa
    return Runa(action_manager)


def _load_fishing(action_manager):
    from src.fishing import Pesca
    return Pesca(action_manager)


def _require_action_manager(action_name: str):
    if appController._actionManager is None:
        return False, f"Selecione uma janela antes de {action_name}."
    if not appController._actionManager.is_valid():
        appController._actionManager = None
        return False, f"A janela selecionada não está mais válida. Selecione outra antes de {action_name}."
    return True, ""


class AppController:
    def __init__(self):
        self._hwnd = None
        self._actionManager = None
        self._fishing = None
        self._rune = None
        self._training = None


sobrepor_janela = False
windows = []
appController = AppController()
battle_list_region = None

_boot_vleft, _boot_vtop, _boot_vwidth, _boot_vheight = _get_virtual_screen_bounds()
battle_list_validator = BattleListRegionValidator(
    screen_bounds=(_boot_vleft, _boot_vtop, _boot_vwidth, _boot_vheight)
)

battle_monitor_active = False
battle_monitor_job = None
battle_last_scan_at = 0.0
battle_scan_interval_seconds = 1.5  # responsivo para Normal mode (troca rápida de alvo)

_last_normal_attack_at = 0.0
_last_normal_attack_idx = None
_last_summon_attack_at = 0.0
_last_summon_attack_key = None

self_use_var = None
push_item_var = None
training_mode_var = None


# ----- Cores dos botões -----
COLOR_GREEN_STRONG = "#4fbf8b"
COLOR_GREEN_STRONG_ACTIVE = "#5fd3a0"
COLOR_GREEN_OPAQUE = "#3a4a44"
COLOR_GREEN_OPAQUE_FG = "#8f9a94"

COLOR_RED_STRONG = "#d99292"
COLOR_RED_STRONG_ACTIVE = "#8a444a"
COLOR_RED_OPAQUE = "#4a3a3a"
COLOR_RED_OPAQUE_FG = "#9a8f8f"


# ----- Kill switch global (ESC) -----
_global_esc_listener = None
_global_esc_lock = threading.Lock()
_escape_in_progress = threading.Event()


# ----- Hotkey global Shift+F1 -----
_global_macro_hotkey_listener = None
_global_macro_hotkey_lock = threading.Lock()


def _install_global_esc_listener() -> bool:
    global _global_esc_listener
    with _global_esc_lock:
        if _global_esc_listener is not None:
            return True
        try:
            from pynput import keyboard
        except Exception as exc:
            print(f"[esc-global] pynput indisponível: {exc}")
            return False

        def _on_press(key):
            try:
                if key == keyboard.Key.esc:
                    if globals().get("root") is not None:
                        root.after(0, handle_escape)
                    else:
                        handle_escape()
            except Exception as exc:
                print(f"[esc-global] erro no handler: {exc}")
            return True

        listener = keyboard.Listener(on_press=_on_press)
        listener.daemon = True
        listener.start()
        _global_esc_listener = listener
        print("[esc-global] hotkey ESC global instalado.")
        return True


def _uninstall_global_esc_listener() -> None:
    global _global_esc_listener
    with _global_esc_lock:
        if _global_esc_listener is None:
            return
        try:
            _global_esc_listener.stop()
        except Exception:
            pass
        finally:
            _global_esc_listener = None
        print("[esc-global] hotkey ESC global removido.")


def _install_global_macro_hotkey_listener() -> bool:
    global _global_macro_hotkey_listener
    with _global_macro_hotkey_lock:
        if _global_macro_hotkey_listener is not None:
            return True
        try:
            from pynput import keyboard
        except Exception as exc:
            print(f"[macro-hotkey] pynput indisponível: {exc}")
            return False

        def _trigger_start_macro():
            if globals().get("root") is not None:
                root.after(0, _safe_start_macro_rune_from_hotkey)
            else:
                _safe_start_macro_rune_from_hotkey()

        try:
            hotkeys = keyboard.GlobalHotKeys({
                '<shift>+<f1>': _trigger_start_macro,
            })
            hotkeys.daemon = True
            hotkeys.start()
            _global_macro_hotkey_listener = hotkeys
            print("[macro-hotkey] Shift+F1 global instalado.")
            return True
        except Exception as exc:
            print(f"[macro-hotkey] erro ao instalar Shift+F1: {exc}")
            return False


def _uninstall_global_macro_hotkey_listener() -> None:
    global _global_macro_hotkey_listener
    with _global_macro_hotkey_lock:
        if _global_macro_hotkey_listener is None:
            return
        try:
            _global_macro_hotkey_listener.stop()
        except Exception:
            pass
        finally:
            _global_macro_hotkey_listener = None
        print("[macro-hotkey] Shift+F1 global removido.")


def _safe_start_macro_rune_from_hotkey():
    try:
        ok, message = _require_action_manager("iniciar a macro")
        if not ok:
            if "returnBox" in globals() and returnBox is not None:
                returnBox.delete("1.0", tk.END)
                returnBox.insert("1.0", f"[Shift+F1] {message}\n")
            return
        start_macro_rune()
        if "returnBox" in globals() and returnBox is not None:
            returnBox.insert("1.0", "[Shift+F1] macro de runa iniciada.\n")
    except Exception as exc:
        print(f"[macro-hotkey] erro ao iniciar macro: {exc}")


def normalize_hotkey(value):
    return str(value or "").strip().lower()


def sobrepor_todas_janelas():
    global sobrepor_janela
    sobrepor_janela = not sobrepor_janela
    try:
        if globals().get('root') is not None:
            root.attributes('-topmost', sobrepor_janela)
        if globals().get("sobrepor_btn") is not None:
            sobrepor_btn.config(
                text="Sobrepor: ON" if sobrepor_janela else "Sobrepor: OFF",
                bg="#8bd5b5" if sobrepor_janela else "#414954",
            )
    except Exception:
        pass


def handle_escape(event=None):
    if _escape_in_progress.is_set():
        return "break"
    _escape_in_progress.set()
    try:
        stop_battle_monitor()
        if appController._fishing is not None:
            try: appController._fishing.Pescar()
            except Exception as exc: print(f"[esc-global] erro pesca: {exc}")
        if appController._rune is not None:
            try: appController._rune.Atacar(False)
            except Exception as exc: print(f"[esc-global] erro runa: {exc}")
        if appController._training is not None:
            try:
                current = appController._training.state.value
                if current not in ("INATIVO", "PAUSADO"):
                    appController._training.pause()
            except Exception as exc:
                print(f"[esc-global] erro treino: {exc}")

        _refresh_training_buttons()
        _refresh_fishing_buttons()
        _refresh_macro_buttons()
        if "returnBox" in globals() and returnBox is not None:
            returnBox.insert("1.0", "ESC pressionado (global): bots parados.\n")
    finally:
        _escape_in_progress.clear()
    return "break"


# ============================================================
# Helpers de estado dos botões
# ============================================================

def _training_is_busy() -> bool:
    if appController._training is None:
        return False
    try:
        state = appController._training.state.value
    except Exception:
        return False
    return state not in ("INATIVO", "PAUSADO", "ERRO")


def _training_can_stop() -> bool:
    if battle_monitor_active:
        return True
    if appController._training is None:
        return False
    try:
        return appController._training.state.value not in ("INATIVO", "PAUSADO", "ERRO")
    except Exception:
        return False


def _can_start_training() -> bool:
    am = appController._actionManager
    if am is None or not am.is_valid():
        return False
    if battle_list_region is None:
        return False
    try:
        if not battle_list_validator.is_valid(battle_list_region):
            return False
    except Exception:
        return False
    if _training_is_busy():
        return False
    return True


def _fishing_is_active() -> bool:
    fishing = appController._fishing
    if fishing is None:
        return False
    try:
        from src.status import Status
        return fishing.status == Status.Active
    except Exception:
        return False


def _can_start_fishing() -> bool:
    am = appController._actionManager
    if am is None or not am.is_valid():
        return False
    fishing = appController._fishing
    if fishing is None:
        return False
    if getattr(fishing, "varinha", None) is None:
        return False
    if not getattr(fishing, "watersCoords", None):
        return False
    if _fishing_is_active():
        return False
    return True


def _macro_is_active() -> bool:
    rune = appController._rune
    if rune is None:
        return False
    try:
        from src.status import Status
        return rune.status == Status.Active
    except Exception:
        return False


def _can_start_macro() -> bool:
    am = appController._actionManager
    if am is None or not am.is_valid():
        return False
    if _macro_is_active():
        return False
    return True


def _apply_green(button, enabled: bool):
    try:
        if enabled:
            button.config(
                state=tk.NORMAL,
                bg=COLOR_GREEN_STRONG,
                activebackground=COLOR_GREEN_STRONG_ACTIVE,
                disabledforeground=COLOR_GREEN_OPAQUE_FG,
                cursor="hand2",
            )
        else:
            button.config(
                state=tk.DISABLED,
                bg=COLOR_GREEN_OPAQUE,
                activebackground=COLOR_GREEN_OPAQUE,
                disabledforeground=COLOR_GREEN_OPAQUE_FG,
                cursor="arrow",
            )
    except Exception:
        pass


def _apply_red(button, enabled: bool):
    try:
        if enabled:
            button.config(
                state=tk.NORMAL,
                bg=COLOR_RED_STRONG,
                activebackground=COLOR_RED_STRONG_ACTIVE,
                disabledforeground=COLOR_RED_OPAQUE_FG,
                cursor="hand2",
            )
        else:
            button.config(
                state=tk.DISABLED,
                bg=COLOR_RED_OPAQUE,
                activebackground=COLOR_RED_OPAQUE,
                disabledforeground=COLOR_RED_OPAQUE_FG,
                cursor="arrow",
            )
    except Exception:
        pass


def _refresh_training_buttons():
    if globals().get("start_training_btn") is not None:
        _apply_green(start_training_btn, _can_start_training())
    if globals().get("stop_training_btn") is not None:
        _apply_red(stop_training_btn, _training_can_stop())


def _refresh_fishing_buttons():
    if globals().get("start_fishing_btn") is not None:
        _apply_green(start_fishing_btn, _can_start_fishing())
    if globals().get("stop_fishing_btn") is not None:
        _apply_red(stop_fishing_btn, _fishing_is_active())


def _refresh_macro_buttons():
    if globals().get("start_macro_btn") is not None:
        _apply_green(start_macro_btn, _can_start_macro())
    if globals().get("stop_macro_btn") is not None:
        _apply_red(stop_macro_btn, _macro_is_active())


# ============================================================
# Análise da Battle List (HP state + seleção)
# ============================================================

def _analyze_battle_region(region):
    """Retorna lista de dicts com bounds, hp_state e is_selected.

    Estratégia:
      - detecta HP bars via máscara de cor (verde/amarelo/vermelho);
      - agrupa linhas por proximidade vertical;
      - determina hp_state pela cor dominante da barra;
      - determina seleção por contorno vermelho nas bordas da linha
        (acima/abaixo da barra, para não confundir com HP bar vermelha).
    """
    if np is None or region is None:
        return []

    try:
        grabbed = _grab_screen(bbox=region.as_tuple())
        if grabbed is None:
            return []
        arr = np.asarray(grabbed.convert("RGB"), dtype=np.uint8)
    except Exception as exc:
        print(f"[battle-detect] erro na captura: {exc}")
        return []

    height, width = arr.shape[:2]
    if height < 5 or width < 10:
        return []

    start_y = min(25, height // 4)
    play_area = arr[start_y:, :, :]
    if play_area.size == 0:
        return []

    R = play_area[:, :, 0].astype(np.int16)
    G = play_area[:, :, 1].astype(np.int16)
    B = play_area[:, :, 2].astype(np.int16)

    green_bar = ((G >= 65) & (G > R * 1.20) & (G > B * 1.15) & (R < 155) & (B < 155))
    yellow_bar = ((R >= 150) & (G >= 130) & (B < 110)
                  & (R > B * 1.5) & (G > B * 1.3) & (np.abs(R - G) < 70))
    red_bar = ((R >= 100) & (R > G * 1.25) & (R > B * 1.20) & (G < 155))
    bar_mask = green_bar | yellow_bar | red_bar

    min_pixels = max(8, int(width * 0.04))
    min_span = max(12, int(width * 0.06))

    active_rows = []
    for y in range(bar_mask.shape[0]):
        xs = np.flatnonzero(bar_mask[y])
        if len(xs) < min_pixels:
            continue
        if int(xs[-1]) - int(xs[0]) + 1 < min_span:
            continue
        active_rows.append(y)

    if not active_rows:
        return []

    max_vertical_gap = 3
    blocks = []
    current_top = active_rows[0]
    current_bottom = active_rows[0]
    for y in active_rows[1:]:
        if y - current_bottom <= max_vertical_gap + 1:
            current_bottom = y
        else:
            blocks.append((current_top, current_bottom))
            current_top = y
            current_bottom = y
    blocks.append((current_top, current_bottom))

    entities = []
    for top, bottom in blocks:
        bar_height = bottom - top + 1
        if bar_height < 2:
            continue

        # Cor dominante no bloco da barra
        g_count = int(green_bar[top:bottom + 1, :].sum())
        y_count = int(yellow_bar[top:bottom + 1, :].sum())
        r_count = int(red_bar[top:bottom + 1, :].sum())
        counts = {"green": g_count, "yellow": y_count, "red": r_count}
        if max(counts.values()) == 0:
            hp_state = "unknown"
        else:
            hp_state = max(counts, key=counts.get)

        row_top = region.top + start_y + top - 13
        row_bottom = region.top + start_y + bottom + 3
        row_top = max(region.top, row_top)
        row_bottom = min(region.bottom, row_bottom)
        if row_bottom <= row_top:
            continue

        bar_screen_top = region.top + start_y + top
        bar_screen_bottom = region.top + start_y + bottom

        entities.append({
            "bounds": (region.left, row_top, region.right, row_bottom),
            "bar_y": (bar_screen_top, bar_screen_bottom),
            "hp_state": hp_state,
            "is_selected": False,
        })

    entities.sort(key=lambda e: e["bounds"][1])

    # Remove duplicatas próximas
    unique = []
    for e in entities:
        cy = (e["bounds"][1] + e["bounds"][3]) // 2
        if not any(abs(cy - ((o["bounds"][1] + o["bounds"][3]) // 2)) <= 4 for o in unique):
            unique.append(e)
    unique = unique[:20]

    # Detecção de seleção
    for e in unique:
        e["is_selected"] = _is_row_selected(arr, region, e)

    return unique


def _is_row_selected(arr, region, entity):
    """Detecta contorno vermelho do alvo selecionado nas bordas da linha,
    excluindo a área da HP bar (para não confundir HP baixo com seleção)."""
    try:
        l, t, r, b = entity["bounds"]
        bar_t, bar_b = entity["bar_y"]

        local_l = max(0, l - region.left)
        local_r = min(arr.shape[1], r - region.left)

        strips = [
            (max(0, t - region.top), max(0, bar_t - region.top - 1)),      # acima
            (min(arr.shape[0], bar_b - region.top + 1), min(arr.shape[0], b - region.top)),  # abaixo
        ]

        red_total = 0
        pixel_total = 0
        for y0, y1 in strips:
            if y1 <= y0:
                continue
            sub = arr[y0:y1, local_l:local_r]
            if sub.size == 0:
                continue
            sr = sub[:, :, 0].astype(np.int16)
            sg = sub[:, :, 1].astype(np.int16)
            sb = sub[:, :, 2].astype(np.int16)
            mask = (sr > 160) & (sg < 120) & (sb < 120)
            red_total += int(mask.sum())
            pixel_total += sub.shape[0] * sub.shape[1]

        if pixel_total == 0:
            return False
        return (red_total / pixel_total) > 0.03
    except Exception:
        return False


def _get_battle_entities(region):
    """Compat: retorna só os bounds."""
    return [e["bounds"] for e in _analyze_battle_region(region)]


def _get_target_center(snapshot, index):
    if not snapshot or not snapshot.rows or index < 0 or index >= len(snapshot.rows):
        return None
    l, t, r, b = snapshot.rows[index].bounds
    return ((l + r) // 2, (t + b) // 2)


def build_battle_snapshot_from_region(region):
    if region is None:
        return None
    entities = _analyze_battle_region(region)
    if not entities:
        return BattleListSnapshot(
            rows=(),
            state=SelectorState.UNCERTAIN,
            complete=False,
            captured_at=time.time(),
            selected_index=None,
        )

    rows = []
    selected_idx = None
    for index, entity in enumerate(entities[:5]):
        l, t, r, b = entity["bounds"]
        rows.append(BattleListRow(
            index=index,
            bounds=(l, t, r, b),
            confidence=0.98,
            hp_state=entity.get("hp_state", "unknown"),
        ))
        if entity.get("is_selected"):
            selected_idx = index

    return BattleListSnapshot(
        rows=tuple(rows),
        state=SelectorState.VALID,
        complete=True,
        captured_at=time.time(),
        selected_index=selected_idx,
    )


# ============================================================
# Log / monitor
# ============================================================

def _resolve_tesseract_path():
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.join(os.getcwd(), "tesseract", "tesseract.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _extract_battle_creature_names(region):
    if region is None or Image is None:
        return ()

    try:
        import pytesseract
        tp = _resolve_tesseract_path()
        if tp:
            pytesseract.pytesseract.tesseract_cmd = tp
        else:
            try:
                pytesseract.get_tesseract_version()
            except Exception:
                return ()
    except Exception:
        return ()

    try:
        grabbed = _grab_screen(bbox=region.as_tuple())
        if grabbed is None:
            return ()
        image = grabbed.convert("L")
        crop_top = min(25, image.height // 3)
        image = image.crop((0, crop_top, image.width, image.height))
        image = image.point(lambda p: 255 if p > 60 else 0)
        if ImageOps:
            image = ImageOps.invert(image)
        image = image.resize((image.width * 4, image.height * 4), Image.Resampling.LANCZOS)
        text = pytesseract.image_to_string(image, config="--psm 6 --oem 3")
    except Exception:
        return ()

    names = []
    ignore_words = {"battle", "battle list", "monitor", "target", "targets", "screen",
                    "age", "asc", "ex", "cap", "luck", "exp", "hp", "mp", "mana",
                    "soul", "options", "logout", "world", "chat"}
    for raw_line in text.splitlines():
        line = " ".join(raw_line.strip().split())
        if not line:
            continue
        parts = line.split()
        if len(parts) > 1 and len(parts[0]) == 1:
            line = " ".join(parts[1:])
        lowered = line.lower()
        if lowered in ignore_words or any(ign in lowered for ign in ["screen", "asc", "cap", "luck", "ex ", "age"]):
            continue
        if any(ch.isdigit() for ch in line):
            continue
        if len(line) < 2 or len(line) > 40:
            continue
        names.append(line)
    return tuple(names)


# ============================================================
# Execução de ataques
# ============================================================

def _execute_summon_attack(snapshot):
    global _last_summon_attack_at, _last_summon_attack_key
    if snapshot is None or not snapshot.complete or not snapshot.rows:
        return False, "Snapshot inválido."
    if len(snapshot.rows) <= 1:
        return False, "É preciso mais de um alvo visível."
    if snapshot.selected_index is not None:
        return False, "Já existe um alvo selecionado."

    target_pos = _get_target_center(snapshot, 0)
    if target_pos is None:
        return False, "Posição do alvo inválida."

    target_key = tuple((r.index, r.bounds) for r in snapshot.rows[:3])
    now = time.monotonic()
    if target_key == _last_summon_attack_key and (now - _last_summon_attack_at) < 1.2:
        return False, "Aguardando cooldown."

    _last_summon_attack_at = now
    _last_summon_attack_key = target_key

    am = appController._actionManager
    if am is None:
        return False, "Sem action manager."
    am.focusWindow()
    am.move_mouse(target_pos)
    am.left_click(target_pos)
    return True, f"Summon: atacando primeiro alvo em {target_pos}."


def _execute_normal_attack(snapshot):
    global _last_normal_attack_at, _last_normal_attack_idx
    if snapshot is None or not snapshot.complete or not snapshot.rows:
        return False, "Snapshot inválido."

    next_target = appController._training.get_next_target(snapshot)
    if next_target is None:
        return False, "Nenhum alvo elegível."

    if snapshot.selected_index == next_target:
        return False, "Alvo já está selecionado."

    target_pos = _get_target_center(snapshot, next_target)
    if target_pos is None:
        return False, "Posição do alvo inválida."

    now = time.monotonic()
    if _last_normal_attack_idx == next_target and (now - _last_normal_attack_at) < 1.0:
        return False, "Aguardando cooldown."

    _last_normal_attack_at = now
    _last_normal_attack_idx = next_target

    am = appController._actionManager
    if am is None:
        return False, "Sem action manager."
    am.focusWindow()
    am.move_mouse(target_pos)
    am.left_click(target_pos)

    hp = snapshot.rows[next_target].hp_state if next_target < len(snapshot.rows) else "?"
    return True, f"Normal: atacando alvo #{next_target} (HP: {hp}) em {target_pos}."


def execute_first_battle_target_attack():
    if appController._actionManager is None:
        return False, "Selecione uma janela antes de atacar."
    if battle_list_region is None:
        return False, "Selecione a região da Battle List antes de atacar."
    if appController._training is None:
        return False, "Treinamento não inicializado."

    snapshot = build_battle_snapshot_from_region(battle_list_region)
    if snapshot is None:
        return False, "Não foi possível capturar a Battle List."

    if appController._training.mode == TrainingMode.NORMAL_CREATURES:
        return _execute_normal_attack(snapshot)
    return _execute_summon_attack(snapshot)


def tick_training_attack():
    if appController._training is None or battle_list_region is None:
        return False
    snapshot = build_battle_snapshot_from_region(battle_list_region)
    if snapshot is None:
        return False

    if appController._training.mode == TrainingMode.NORMAL_CREATURES:
        ok, _ = _execute_normal_attack(snapshot)
    else:
        ok, _ = _execute_summon_attack(snapshot)
    return bool(ok)


def monitor_battle_region():
    global battle_monitor_active, battle_monitor_job, battle_last_scan_at
    if not battle_monitor_active or battle_list_region is None or appController._training is None:
        battle_monitor_active = False
        return

    battle_last_scan_at = time.monotonic()

    snapshot = build_battle_snapshot_from_region(battle_list_region)
    if snapshot is not None and snapshot.rows:
        mode = appController._training.mode
        count = len(snapshot.rows)
        sel = snapshot.selected_index
        if mode == TrainingMode.NORMAL_CREATURES:
            try:
                nxt = appController._training.get_next_target(snapshot)
            except Exception:
                nxt = None
            hps = ",".join(f"{i}:{r.hp_state}" for i, r in enumerate(snapshot.rows))
            print(f"[battle-monitor][normal] {count} alvos | selected={sel} | next={nxt} | {hps}")
        else:
            print(f"[battle-monitor][summon] {count} alvos | selected={sel}")

    if tick_training_attack():
        print("[battle-monitor] ataque executado.")

    if globals().get("root") is not None and battle_monitor_active:
        battle_monitor_job = root.after(int(battle_scan_interval_seconds * 1000), monitor_battle_region)


def start_battle_monitor():
    global battle_monitor_active, battle_monitor_job, battle_last_scan_at
    if battle_list_region is None:
        print("[battle-monitor] selecione a região da Battle List antes de iniciar.")
        return
    battle_monitor_active = True
    battle_last_scan_at = 0.0
    if globals().get("root") is not None and battle_monitor_job is None:
        battle_monitor_job = root.after(int(battle_scan_interval_seconds * 1000), monitor_battle_region)
    _refresh_training_buttons()


def stop_battle_monitor():
    global battle_monitor_active, battle_monitor_job, battle_last_scan_at
    battle_monitor_active = False
    if globals().get("root") is not None and battle_monitor_job is not None:
        try:
            root.after_cancel(battle_monitor_job)
        except Exception:
            pass
    battle_monitor_job = None
    battle_last_scan_at = 0.0
    print("[battle-monitor] monitor da battle parado.")
    _refresh_training_buttons()


# ============================================================
# Handlers de janela
# ============================================================

def get_windows():
    global windows
    from src.window_handler import getWindows
    returnBox.delete("1.0", tk.END)
    try:
        windows = getWindows(None)
        window_titles = [f"{title} ({hwnd})" for title, hwnd in windows] if windows else []
        combo['values'] = window_titles
        if window_titles:
            combo.set(window_titles[0])
            returnBox.insert("1.0", f"Found {len(window_titles)} windows.\n")
        else:
            combo.set('')
            returnBox.insert("1.0", "No windows found.\n")
    except Exception as e:
        returnBox.insert("1.0", f"Error getting windows: {str(e)}\n")


def select_window():
    selected = combo.get()
    if not selected:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Please select a window first.\n")
        return
    try:
        hwnd = int(selected.split('(')[-1].strip(')'))
        title = selected.rsplit(' (', 1)[0]
        if hwnd:
            appController._hwnd = hwnd
            try:
                appController._actionManager = _load_action_manager(hwnd)
            except Exception as exc:
                returnBox.delete("1.0", tk.END)
                returnBox.insert("1.0", f"Não foi possível inicializar o controlador: {exc}\n")
                return
            if not appController._actionManager.is_valid():
                appController._actionManager = None
                returnBox.delete("1.0", tk.END)
                returnBox.insert("1.0", "A janela selecionada não está ativa ou não é válida.\n")
                _refresh_training_buttons()
                _refresh_fishing_buttons()
                _refresh_macro_buttons()
                return
            returnBox.delete("1.0", tk.END)
            returnBox.insert("1.0", f"Selected window: {title}\nHWND: {hwnd}\n")
            _refresh_training_buttons()
            _refresh_fishing_buttons()
            _refresh_macro_buttons()
        else:
            returnBox.delete("1.0", tk.END)
            returnBox.insert("1.0", "Selected window not found in list.\n")
    except Exception as e:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"Error selecting window: {str(e)}\n")


# ============================================================
# Handlers de runa / macro
# ============================================================

def _ensure_rune():
    if not appController._rune:
        appController._rune = _load_runa(appController._actionManager)
    return appController._rune


def _sync_flags_for_hotkey(hotkey_name):
    """Atualiza os checkboxes para refletir o estado persistido do hotkey."""
    if appController._rune and hotkey_name:
        self_use_var.set(appController._rune.is_self_use_enabled(hotkey_name))
        push_item_var.set(appController._rune.is_push_item_enabled(hotkey_name))


def _apply_flags_to_hotkey(hotkey_name):
    """Aplica o estado dos checkboxes ao hotkey atual na Runa."""
    if not appController._rune or not hotkey_name:
        return
    is_push = bool(push_item_var.get())
    is_self = bool(self_use_var.get())
    if is_push and is_self:
        # Segurança extra: push vence
        is_self = False
        self_use_var.set(False)
    appController._rune.set_self_use(hotkey_name, is_self)
    appController._rune.set_push_item(hotkey_name, is_push)


def search_runa():
    ok, message = _require_action_manager("capturar a runa")
    if not ok:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"{message}\n")
        return
    _ensure_rune()
    returnBox.delete("1.0", tk.END)

    hotkey_name = normalize_hotkey(key.get())
    if not hotkey_name:
        returnBox.insert("1.0", "Informe uma hotkey antes de capturar.\n")
        return

    if push_item_var.get() and self_use_var.get():
        returnBox.insert("1.0", "Self Use e Push Item não podem estar ligados juntos.\n")
        return

    _apply_flags_to_hotkey(hotkey_name)
    is_push = appController._rune.is_push_item_enabled(hotkey_name)

    buf = io.StringIO()
    success = False
    with contextlib.redirect_stdout(buf):
        if is_push:
            success = appController._rune.getDragPoints(key_name=hotkey_name)
        else:
            success = appController._rune.getRuna(key_name=hotkey_name)
    if success:
        key_entry.delete(0, tk.END)

    out = buf.getvalue() or "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


def capture_player_position():
    ok, message = _require_action_manager("capturar a posição do player")
    if not ok:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"{message}\n")
        return
    _ensure_rune()
    appController._rune.load_mappings(merge_existing=True)
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        captured = appController._rune.getPlayerPosition()
        if captured:
            appController._rune.save_mappings()
    out = buf.getvalue() or "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


def update_self_use_mode():
    # Mutual exclusion: se ligou self_use, desliga push_item
    if self_use_var.get() and push_item_var.get():
        push_item_var.set(False)
    hotkey_name = normalize_hotkey(key.get())
    _apply_flags_to_hotkey(hotkey_name)


def update_push_item_mode():
    # Mutual exclusion: se ligou push_item, desliga self_use
    if push_item_var.get() and self_use_var.get():
        self_use_var.set(False)
    hotkey_name = normalize_hotkey(key.get())
    _apply_flags_to_hotkey(hotkey_name)


def sync_self_use_mode(event=None):
    hotkey_name = normalize_hotkey(key.get())
    _sync_flags_for_hotkey(hotkey_name)


def load_runa():
    _ensure_rune()
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.load_mappings()
    sync_self_use_mode()
    out = buf.getvalue() or "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


def save_runa():
    _ensure_rune()
    hotkey_name = normalize_hotkey(key.get())
    if hotkey_name:
        _apply_flags_to_hotkey(hotkey_name)
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.save_mappings()
    out = buf.getvalue() or "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


def list_runa():
    _ensure_rune()
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.list_mappings()
    out = buf.getvalue() or "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


def reset_runa():
    _ensure_rune()
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.resetRuna(key_name=normalize_hotkey(key.get()))
    key_entry.delete(0, tk.END)
    out = buf.getvalue() or "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


def start_macro_rune():
    ok, message = _require_action_manager("iniciar a macro")
    if not ok:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"{message}\n")
        return
    _ensure_rune()
    _apply_flags_to_hotkey(normalize_hotkey(key.get()))
    appController._rune.Atacar(True)
    _refresh_macro_buttons()
    _refresh_training_buttons()


def stop_macro_rune():
    _ensure_rune()
    try:
        appController._rune.Atacar(False)
    except Exception:
        _refresh_macro_buttons()
        _refresh_training_buttons()
        return
    _refresh_macro_buttons()
    _refresh_training_buttons()


# ============================================================
# Handlers de pesca
# ============================================================

def reset_coordinates():
    ok, message = _require_action_manager("resetar a pesca")
    if not ok:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"{message}\n")
        return
    if not appController._fishing:
        appController._fishing = _load_fishing(appController._actionManager)
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._fishing.resetCoordinates()
    out = buf.getvalue() or "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)
    _refresh_fishing_buttons()


def search_varinha():
    ok, message = _require_action_manager("capturar a varinha")
    if not ok:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"{message}\n")
        return
    if not appController._fishing:
        appController._fishing = _load_fishing(appController._actionManager)
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._fishing.getFishingRod()
    out = buf.getvalue() or "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)
    _refresh_fishing_buttons()


def search_aguas():
    ok, message = _require_action_manager("capturar as águas")
    if not ok:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"{message}\n")
        return
    if not appController._fishing:
        appController._fishing = _load_fishing(appController._actionManager)
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._fishing.getWaters()
    out = buf.getvalue() or "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)
    _refresh_fishing_buttons()


def start_pesca():
    ok, message = _require_action_manager("iniciar a pesca")
    if not ok:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"{message}\n")
        return
    if not appController._fishing:
        appController._fishing = _load_fishing(appController._actionManager)
    if appController._fishing.varinha is None:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Necessário definir a varinha antes de iniciar.\n")
        return
    if not appController._fishing.watersCoords:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Necessário definir ao menos uma água antes de iniciar.\n")
        return
    appController._fishing.Pescar()
    _refresh_fishing_buttons()
    _refresh_training_buttons()


def stop_pesca():
    if not appController._fishing:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Bot de pesca não está inicializado.\n")
        return
    appController._fishing.Pescar()
    returnBox.delete("1.0", tk.END)
    returnBox.insert("1.0", "Pesca parada.\n")
    _refresh_fishing_buttons()
    _refresh_training_buttons()


# ============================================================
# Treino
# ============================================================

def start_treino():
    mode_str = training_mode_var.get() if training_mode_var is not None else "summon"
    mode = TrainingMode.SUMMON_CREATURES if mode_str == "summon" else TrainingMode.NORMAL_CREATURES

    if not appController._training:
        appController._training = TrainingStateMachine(mode=mode)
    else:
        appController._training.set_mode(mode)

    appController._training.start()
    start_battle_monitor()

    snapshot = build_battle_snapshot_from_region(battle_list_region)
    if snapshot is None:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Treinamento aguardando região da Battle List.\n")
        _refresh_training_buttons()
        return

    mode_label = "Summon Creatures" if mode == TrainingMode.SUMMON_CREATURES else "Normal Creatures"

    if mode == TrainingMode.SUMMON_CREATURES and len(snapshot.rows) < 2:
        decision = appController._training.evaluate_battle_list(snapshot)
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0",
            f"Modo: {mode_label}\n"
            f"Treinamento aguardando ≥2 alvos.\n"
            f"Estado: {appController._training.state.value}\nMotivo: {decision.reason}\n")
        _refresh_training_buttons()
        return

    appController._training.train()
    decision = appController._training.evaluate_battle_list(snapshot)
    next_target = appController._training.get_next_target(snapshot)
    ok, message = execute_first_battle_target_attack()

    hp_line = ""
    try:
        hp_line = " | ".join(f"#{i}:{r.hp_state}" for i, r in enumerate(snapshot.rows[:5]))
    except Exception:
        pass

    returnBox.delete("1.0", tk.END)
    returnBox.insert("1.0",
        f"Treinamento ativo — Modo: {mode_label}\n"
        f"Estado: {appController._training.state.value}\n"
        f"Região: {battle_list_region.left},{battle_list_region.top},"
        f"{battle_list_region.width},{battle_list_region.height}\n"
        f"Próximo alvo: {next_target} | selected_index: {snapshot.selected_index}\n"
        f"Alvos elegíveis: {decision.eligible_targets} | Protegido: {decision.protected_index}\n"
        f"HP: {hp_line}\n"
        f"Ação: {'ok' if ok else 'aguardando'}\nDetalhe: {message}\n")
    _refresh_training_buttons()


def stop_treino():
    if not appController._training:
        appController._training = TrainingStateMachine()
    stop_battle_monitor()
    try:
        current = appController._training.state.value
        if current not in ("INATIVO", "PAUSADO"):
            appController._training.pause()
    except Exception:
        pass
    returnBox.delete("1.0", tk.END)
    returnBox.insert("1.0", f"Treinamento pausado.\nEstado: {appController._training.state.value}\n")
    _refresh_training_buttons()


# ============================================================
# Seleção de região
# ============================================================

def configure_battle_list_region(region):
    global battle_list_region, battle_list_validator
    if region is None:
        return
    vleft, vtop, vwidth, vheight = _get_virtual_screen_bounds()
    battle_list_validator = BattleListRegionValidator(
        screen_bounds=(vleft, vtop, vwidth, vheight)
    )
    battle_list_region = region
    if battle_list_validator.is_valid(region):
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0",
            f"Região da Battle List validada.\n"
            f"X: {region.left} Y: {region.top} L: {region.width} A: {region.height}\n"
            f"Desktop virtual: origem ({vleft}, {vtop}) {vwidth}x{vheight}\n")
    else:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Região inválida. Ajuste a seleção.\n")
    _refresh_training_buttons()


def preview_battle_list_capture():
    global battle_list_region
    if ImageTk is None:
        returnBox.insert("1.0", "Pillow não disponível para pré-visualização.\n")
        return
    if battle_list_region is None or not battle_list_validator.is_valid(battle_list_region):
        returnBox.insert("1.0", "Selecione primeiro uma região válida.\n")
        return
    grabbed = _grab_screen(bbox=battle_list_region.as_tuple())
    if grabbed is None:
        returnBox.insert("1.0", "Não foi possível capturar a região.\n")
        return
    preview = tk.Toplevel(root)
    preview.title("Prévia da Battle List")
    preview.attributes("-topmost", True)
    photo = ImageTk.PhotoImage(grabbed)
    label = tk.Label(preview, image=photo)
    label.image = photo
    label.grid(padx=12, pady=12)
    preview.transient(root)
    preview.grab_set()


def select_battle_list_region():
    if ImageTk is None:
        returnBox.insert("1.0", "Captura indisponível neste ambiente.\n")
        return

    vleft, vtop, vwidth, vheight = _get_virtual_screen_bounds()
    screen = _grab_screen(bbox=None)
    if screen is None:
        returnBox.insert("1.0", "Não foi possível capturar o desktop virtual.\n")
        return

    overlay = tk.Toplevel(root)
    overlay.attributes("-topmost", True)
    overlay.geometry(f"{vwidth}x{vheight}{vleft:+d}{vtop:+d}")
    overlay.overrideredirect(True)
    overlay.wm_attributes("-alpha", 0.28)

    canvas = tk.Canvas(overlay, width=vwidth, height=vheight, cursor="crosshair",
                       bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    photo = ImageTk.PhotoImage(screen)
    canvas.create_image(0, 0, image=photo, anchor="nw")
    canvas.image = photo  # type: ignore[attr-defined]

    selection_id = None
    start_x = start_y = None

    def start_selection(event):
        nonlocal selection_id, start_x, start_y
        start_x, start_y = event.x, event.y
        if selection_id is not None:
            canvas.delete(selection_id)
        selection_id = canvas.create_rectangle(start_x, start_y, event.x, event.y,
                                               outline="#77dd77", width=2)

    def draw_rectangle(event):
        nonlocal selection_id, start_x, start_y
        if selection_id is None or start_x is None or start_y is None:
            return
        canvas.coords(selection_id, start_x, start_y, event.x, event.y)

    def finish_selection(event):
        nonlocal start_x, start_y, selection_id
        if start_x is None or start_y is None:
            overlay.destroy()
            return
        left = vleft + min(start_x, event.x)
        top = vtop + min(start_y, event.y)
        width = abs(event.x - start_x)
        height = abs(event.y - start_y)
        selection = BattleListRegion(
            left=left, top=top,
            width=max(width, 1), height=max(height, 1), monitor=1,
        )
        configure_battle_list_region(selection)
        overlay.destroy()

    canvas.bind("<ButtonPress-1>", start_selection)
    canvas.bind("<B1-Motion>", draw_rectangle)
    canvas.bind("<ButtonRelease-1>", finish_selection)
    overlay.bind("<Escape>", lambda event: overlay.destroy())
    overlay.focus_force()


# ============================================================
# UI
# ============================================================

class _Tooltip:
    def __init__(self, widget, text: str, delay_ms: int = 350):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id = None
        self._tip_window = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        if self._tip_window is not None:
            return
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() + 6
            y = self.widget.winfo_rooty() + 2
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tip.attributes("-topmost", True)
            frame = tk.Frame(tip, bg="#20252b", highlightthickness=1, highlightbackground="#454d58")
            frame.pack()
            tk.Label(frame, text=self.text, bg="#20252b", fg="#eef2f7",
                     font=("Segoe UI", 8), justify="left",
                     padx=8, pady=6, wraplength=280).pack()
            self._tip_window = tip
        except Exception:
            self._tip_window = None

    def _hide(self, _event=None):
        self._cancel()
        if self._tip_window is not None:
            try:
                self._tip_window.destroy()
            except Exception:
                pass
            self._tip_window = None


def _make_stateful_button(parent, text, command):
    return tk.Button(
        parent, text=text, command=command,
        bg=COLOR_GREEN_OPAQUE, fg="#142c23",
        activebackground=COLOR_GREEN_STRONG_ACTIVE, activeforeground="#142c23",
        disabledforeground=COLOR_GREEN_OPAQUE_FG,
        bd=0, relief="flat", highlightthickness=0,
        font=("Segoe UI", 7, "bold"), padx=3, pady=4, wraplength=145,
        cursor="arrow",
    )


def build_ui():
    _enable_dpi_awareness()

    global root, combo, returnBox, key, key_entry, sobrepor_btn
    global self_use_var, push_item_var, training_mode_var
    global macro_rune_start_btn, macro_rune_stop_btn
    global start_btn, stop_btn, busca_varinha_btn, busca_water_btn
    global start_training_btn, stop_training_btn
    global start_fishing_btn, stop_fishing_btn
    global start_macro_btn, stop_macro_btn

    root = tk.Tk()
    root.title("Exordion 7.4 Pro")
    root.geometry("660x460")
    root.minsize(620, 420)
    root.configure(bg="#252a31")
    root.resizable(True, True)

    BG = "#252a31"
    PANEL = "#30363f"
    FG = "#eef2f7"
    MUTED = "#d0d7df"
    BORDER = "#454d58"

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Compact.TCombobox", fieldbackground="#20252b",
                    background="#414954", foreground=FG, arrowcolor=FG, padding=2)
    style.map(
        "Compact.TCombobox",
        fieldbackground=[("disabled", PANEL), ("readonly", "#20252b")],
        foreground=[("disabled", MUTED), ("readonly", FG)],
        background=[("pressed", "#596575"), ("active", "#596575")],
        arrowcolor=[("disabled", MUTED)],
    )

    root.columnconfigure(0, weight=1)
    root.rowconfigure(3, weight=1)

    header = tk.Frame(root, bg=BG)
    header.grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 2))
    header.columnconfigure(0, weight=1)
    tk.Label(header, text="Exordion 7.4 Pro", bg=BG, fg=FG,
             font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")

    header_right = tk.Frame(header, bg=BG)
    header_right.grid(row=0, column=1, sticky="e")
    tk.Label(header_right, text="● Pronto", bg=BG, fg="#9af0c5",
             font=("Segoe UI", 8, "bold")).grid(row=0, column=0, padx=(0, 8), sticky="e")
    sobrepor_btn = tk.Button(
        header_right, text="Sobrepor: OFF", command=sobrepor_todas_janelas,
        bg="#414954", fg="#eef2f7", activebackground="#596575",
        activeforeground="#eef2f7", bd=0, relief="flat", highlightthickness=0,
        font=("Segoe UI", 7, "bold"), padx=6, pady=3, cursor="hand2",
    )
    sobrepor_btn.grid(row=0, column=1, sticky="e")

    content = tk.Frame(root, bg=BG)
    content.grid(row=1, column=0, sticky="ew", padx=6)
    content.columnconfigure(0, weight=1, uniform="columns")
    content.columnconfigure(1, weight=1, uniform="columns")

    def make_panel(parent, title, row, column, tooltip_text=None):
        panel = tk.Frame(parent, bg=PANEL, bd=0, padx=7, pady=6,
                         highlightthickness=1, highlightbackground=BORDER)
        panel.grid(row=row, column=column, sticky="nsew", padx=3, pady=3)
        panel.columnconfigure(0, weight=1)
        title_row = tk.Frame(panel, bg=PANEL)
        title_row.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        title_row.columnconfigure(0, weight=1)
        tk.Label(title_row, text=title.upper(), bg=PANEL, fg=FG,
                 font=("Segoe UI", 8, "bold"), anchor="w").grid(row=0, column=0, sticky="w")
        if tooltip_text:
            help_btn = tk.Label(title_row, text="?", bg=PANEL, fg="#9af0c5",
                                font=("Segoe UI", 9, "bold"),
                                cursor="question_arrow", padx=4)
            help_btn.grid(row=0, column=1, sticky="e")
            _Tooltip(help_btn, tooltip_text)
        return panel

    def make_button(parent, text, command=None, kind="secondary", state=tk.NORMAL):
        colors = {
            "primary": ("#8bd5b5", "#2f7c60", "#142c23", "#46534d"),
            "secondary": ("#d8dfe4", "#9daab6", "#202833", "#46515d"),
            "warning": ("#e3c47d", "#a46d14", "#30250e", "#514a39"),
            "danger": ("#d99292", "#8a444a", "#321719", "#513d3f"),
            "dark": ("#414954", "#596575", FG, "#d0d7df"),
        }
        fill, active, foreground, disabled_foreground = colors[kind]
        return tk.Button(parent, text=text, command=command, state=state,
                         bg=fill, fg=foreground, activebackground=active,
                         activeforeground=FG, disabledforeground=disabled_foreground,
                         bd=0, relief="flat", highlightthickness=0,
                         font=("Segoe UI", 7, "bold"), padx=3, pady=4,
                         wraplength=145, cursor="hand2")

    # ----- Painel: Selecionar Janela -----
    panel_window = make_panel(content, "Selecionar janela", 0, 0)
    combo = ttk.Combobox(panel_window, state="readonly",
                         style="Compact.TCombobox", width=22)
    combo.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))
    make_button(panel_window, "Listar janelas", get_windows).grid(
        row=2, column=0, sticky="ew", padx=(0, 2))
    make_button(panel_window, "Selecionar", select_window).grid(
        row=2, column=1, sticky="ew", padx=(2, 0))

    # ----- Painel: Controles de Treino -----
    panel_training = make_panel(content, "Controles de treino", 0, 1)
    panel_training.columnconfigure(0, weight=1)
    panel_training.columnconfigure(1, weight=1)

    # Linha 1: modos (radio)
    mode_row = tk.Frame(panel_training, bg=PANEL)
    mode_row.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))

    training_mode_var = StringVar(value="summon")
    tk.Radiobutton(
        mode_row, text="Summon Creatures", variable=training_mode_var, value="summon",
        bg=PANEL, fg=FG, activebackground=PANEL, activeforeground=FG,
        selectcolor="#20252b", font=("Segoe UI", 8, "bold"),
    ).grid(row=0, column=0, sticky="w", padx=(0, 10))
    tk.Radiobutton(
        mode_row, text="Normal Creatures", variable=training_mode_var, value="normal",
        bg=PANEL, fg=FG, activebackground=PANEL, activeforeground=FG,
        selectcolor="#20252b", font=("Segoe UI", 8, "bold"),
    ).grid(row=0, column=1, sticky="w")

    # Linha 2: iniciar/parar
    start_training_btn = _make_stateful_button(panel_training, "Iniciar treino", start_treino)
    start_training_btn.grid(row=2, column=0, sticky="ew", padx=(0, 2), pady=(0, 3))
    stop_training_btn = _make_stateful_button(panel_training, "Parar treino", stop_treino)
    stop_training_btn.config(fg="#321719")
    stop_training_btn.grid(row=2, column=1, sticky="ew", padx=(2, 0), pady=(0, 3))

    # Linha 3: selecionar região / testar
    make_button(panel_training, "Selecionar região Battle List",
                select_battle_list_region, "dark").grid(
        row=3, column=0, sticky="ew", padx=(0, 2))
    make_button(panel_training, "Testar captura",
                preview_battle_list_capture).grid(
        row=3, column=1, sticky="ew", padx=(2, 0))

    # ----- Painel: Pesca -----
    panel_fishing = make_panel(content, "Controles de pesca", 1, 0)
    for col in range(2):
        panel_fishing.columnconfigure(col, weight=1, uniform="fishing")

    varinha_btn = make_button(panel_fishing, "Capturar varinha", search_varinha)
    varinha_btn.grid(row=1, column=0, sticky="ew", padx=(0, 2), pady=(0, 3))
    aguas_btn = make_button(panel_fishing, "Capturar águas", search_aguas)
    aguas_btn.grid(row=1, column=1, sticky="ew", padx=(2, 0), pady=(0, 3))

    start_fishing_btn = _make_stateful_button(panel_fishing, "Iniciar pesca", start_pesca)
    start_fishing_btn.grid(row=2, column=0, sticky="ew", padx=(0, 2))
    stop_fishing_btn = _make_stateful_button(panel_fishing, "Parar pesca", stop_pesca)
    stop_fishing_btn.config(fg="#321719")
    stop_fishing_btn.grid(row=2, column=1, sticky="ew", padx=(2, 0))
    make_button(panel_fishing, "Resetar pesca", reset_coordinates).grid(
        row=3, column=0, columnspan=2, sticky="ew", pady=(3, 0))

    # ----- Painel: Presets e Macros -----
    panel_macros = make_panel(
        content, "Presets e macros", 1, 1,
        tooltip_text=(
            "Shift+F1 inicia a macro de runa automaticamente.\n"
            "ESC para tudo.\n\n"
            "Self Use: clique direito na runa + clique esquerdo no player.\n"
            "Push Item: drag-and-drop do ponto 1 até o ponto 2 "
            "(ex.: recarregar arrows/bolts).\n"
            "Só um dos dois flags pode estar ligado por hotkey."
        ),
    )
    for col in range(3):
        panel_macros.columnconfigure(col, weight=1, uniform="macros")

    make_button(panel_macros, "Carregar", load_runa).grid(
        row=1, column=0, sticky="ew", padx=(0, 2), pady=(0, 3))
    make_button(panel_macros, "Salvar", save_runa).grid(
        row=1, column=1, sticky="ew", padx=2, pady=(0, 3))
    make_button(panel_macros, "Listar", list_runa).grid(
        row=1, column=2, sticky="ew", padx=(2, 0), pady=(0, 3))

    make_button(panel_macros, "Capturar runa", search_runa).grid(
        row=2, column=0, sticky="ew", padx=(0, 2), pady=(0, 3))
    start_macro_btn = _make_stateful_button(panel_macros, "Iniciar macro", start_macro_rune)
    start_macro_btn.grid(row=2, column=1, sticky="ew", padx=(2, 2), pady=(0, 3))
    stop_macro_btn = _make_stateful_button(panel_macros, "Parar macro", stop_macro_rune)
    stop_macro_btn.config(fg="#321719")
    stop_macro_btn.grid(row=2, column=2, sticky="ew", padx=(2, 0), pady=(0, 3))

    make_button(panel_macros, "Capturar player", capture_player_position).grid(
        row=3, column=0, sticky="ew", padx=(0, 2), pady=(3, 0))

    # Linha de flags: Self use | Push item (mutuamente exclusivos)
    flags_row = tk.Frame(panel_macros, bg=PANEL)
    flags_row.grid(row=3, column=1, columnspan=2, sticky="w", padx=4, pady=(3, 0))

    self_use_var = BooleanVar(value=False)
    push_item_var = BooleanVar(value=False)

    tk.Checkbutton(
        flags_row, text="Self use", variable=self_use_var,
        command=update_self_use_mode,
        bg=PANEL, fg=FG, activebackground=PANEL, activeforeground=FG,
        selectcolor="#20252b", font=("Segoe UI", 8, "bold"),
    ).grid(row=0, column=0, sticky="w")
    tk.Checkbutton(
        flags_row, text="Push item", variable=push_item_var,
        command=update_push_item_mode,
        bg=PANEL, fg=FG, activebackground=PANEL, activeforeground=FG,
        selectcolor="#20252b", font=("Segoe UI", 8, "bold"),
    ).grid(row=0, column=1, sticky="w", padx=(10, 0))

    make_button(panel_macros, "Resetar runas", reset_runa).grid(
        row=4, column=0, columnspan=3, sticky="ew", pady=(3, 0))

    # ----- Hotkey -----
    hotkey_frame = tk.Frame(root, bg=BG)
    hotkey_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 3))
    tk.Label(hotkey_frame, text="Hotkey", bg=BG, fg=MUTED,
             font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 7))

    key = StringVar(value="F5")
    key_entry = tk.Entry(
        hotkey_frame, textvariable=key, width=8,
        bg="#20252b", fg=FG, insertbackground=FG, relief="flat",
        highlightthickness=1, highlightbackground=BORDER,
        highlightcolor="#82aaff", font=("Consolas", 8),
    )
    key_entry.grid(row=0, column=1, sticky="w")
    key_entry.bind(
        "<KeyRelease>",
        lambda event: (key.set(normalize_hotkey(key.get())), sync_self_use_mode()),
    )

    root.bind_all("<Escape>", handle_escape)
    _install_global_esc_listener()
    _install_global_macro_hotkey_listener()

    def _on_close():
        _uninstall_global_esc_listener()
        _uninstall_global_macro_hotkey_listener()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)

    # ----- Console -----
    console = tk.Frame(root, bg="#20252b", highlightbackground=BORDER, highlightthickness=1)
    console.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 8))
    console.columnconfigure(0, weight=1)
    console.rowconfigure(1, weight=1)

    tk.Label(console, text="CONSOLE", bg="#20252b", fg=MUTED,
             font=("Segoe UI", 8, "bold"), anchor="w").grid(
        row=0, column=0, sticky="ew", padx=6, pady=(4, 1))

    returnBox = tk.Text(
        console, bg="#20252b", fg=FG, insertbackground=FG,
        selectbackground="#526b82", selectforeground=FG,
        relief="flat", height=4, font=("Consolas", 8),
        wrap="word", padx=6, pady=4, borderwidth=0,
    )
    returnBox.grid(row=1, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(console, orient="vertical", command=returnBox.yview)
    scrollbar.grid(row=1, column=1, sticky="ns")
    returnBox.configure(yscrollcommand=scrollbar.set)
    returnBox.insert(
        "1.0",
        "Exordion 7.4 Pro pronto. Selecione uma janela para começar.\n"
        "Modo padrão de treino: Summon Creatures.\n",
    )

    # Aliases legados usados por select_window()
    start_btn = start_fishing_btn
    stop_btn = stop_fishing_btn
    busca_varinha_btn = varinha_btn
    busca_water_btn = aguas_btn
    macro_rune_start_btn = start_macro_btn
    macro_rune_stop_btn = stop_macro_btn

    _refresh_training_buttons()
    _refresh_fishing_buttons()
    _refresh_macro_buttons()

    root.update_idletasks()
    width, height = 660, 460
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")
    root.mainloop()


# ============================================================
# Entry points
# ============================================================

def run_demo():
    print("Exordion 7.4 Pro - modo de demonstração")
    vleft, vtop, vwidth, vheight = _get_virtual_screen_bounds()
    print(f"Desktop virtual: origem ({vleft}, {vtop}) tamanho {vwidth}x{vheight}")
    print(f"mss disponível: {_mss_module is not None}")
    return 0


def main(argv=None):
    _enable_dpi_awareness()

    parser = argparse.ArgumentParser(description="Exordion 7.4 Pro")
    parser.add_argument("--demo", action="store_true",
                        help="executa a versão em modo console")
    parser.add_argument("--gui", action="store_true",
                        help="força a interface gráfica")
    args = parser.parse_args(argv)

    if args.demo:
        return run_demo()

    if args.gui:
        try:
            build_ui()
            return 0
        except Exception as exc:
            print(f"GUI não pôde abrir: {type(exc).__name__}: {exc}")
            return 1

    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        try:
            build_ui()
            return 0
        except Exception:
            return run_demo()

    try:
        build_ui()
        return 0
    except Exception:
        return run_demo() if not args.gui else 1


if __name__ == "__main__":
    raise SystemExit(main())
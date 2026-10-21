import argparse
import contextlib
import io
import logging
import os
import threading
import time
import tkinter as tk
from tkinter import N, S, W, E, StringVar, ttk

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

from src.battle_list_selector import (
    BattleListRegion,
    BattleListRegionValidator,
    BattleListRow,
    BattleListSnapshot,
    SafeBattleListTargetSelector,
    SelectorState,
)
from src.training import TrainingStateMachine

# Silencia os avisos de debug do Tesseract
logging.getLogger('pytesseract').setLevel(logging.CRITICAL)


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
battle_list_validator = BattleListRegionValidator(screen_size=(1920, 1080))
battle_monitor_active = False
battle_monitor_job = None
battle_last_region_signature = None
battle_last_detected_names = ()
battle_last_change_log_at = 0.0
battle_last_scan_at = 0.0
battle_scan_interval_seconds = 10.0
battle_last_attack_at = 0.0
battle_last_attack_key = None

# ----- Kill switch global (ESC) -----
_global_esc_listener = None
_global_esc_lock = threading.Lock()
_escape_in_progress = threading.Event()


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


def normalize_hotkey(value):
    return str(value or "").strip().lower()


def sobrepor_todas_janelas():
    global sobrepor_janela
    sobrepor_janela = not sobrepor_janela
    try:
        if globals().get('root') is not None:
            root.attributes('-topmost', sobrepor_janela)
        if sobrepor_btn:
            sobrepor_btn.config(text="Sobrepor: ON" if sobrepor_janela else "Sobrepor: OFF", bg="#8bd5b5" if sobrepor_janela else "#414954")
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
            appController._training.pause()

        if "start_btn" in globals() and start_btn is not None: start_btn.config(state=tk.NORMAL)
        if "stop_btn" in globals() and stop_btn is not None: stop_btn.config(state=tk.DISABLED)
        if "macro_rune_start_btn" in globals() and macro_rune_start_btn is not None: macro_rune_start_btn.config(state=tk.NORMAL)
        if "macro_rune_stop_btn" in globals() and macro_rune_stop_btn is not None: macro_rune_stop_btn.config(state=tk.DISABLED)
        if "returnBox" in globals() and returnBox is not None: returnBox.insert("1.0", "ESC pressionado (global): bots parados.\n")
    finally:
        _escape_in_progress.clear()
    return "break"


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
    if ImageGrab is None or region is None or Image is None:
        return ()

    try:
        import pytesseract
        tesseract_path = _resolve_tesseract_path()
        if tesseract_path:
            pytesseract.pytesseract.tesseract_cmd = tesseract_path
        else:
            try:
                pytesseract.get_tesseract_version()
            except Exception:
                return ()
    except Exception:
        return ()

    try:
        image = ImageGrab.grab(bbox=region.as_tuple()).convert("L")
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
    ignore_words = {"battle", "battle list", "monitor", "target", "targets", "screen", "age", "asc", "ex", "cap", "luck", "exp", "hp", "mp", "mana", "soul", "options", "logout", "world", "chat"}

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


def _get_battle_region_signature(region):
    if ImageGrab is None or region is None:
        return None
    try:
        image = ImageGrab.grab(bbox=region.as_tuple()).convert("RGB")
        return (image.size[0], image.size[1], image.tobytes())
    except Exception:
        return None


def tick_training_attack():
    if appController._training is None or battle_list_region is None:
        return False

    for _ in range(3):
        if should_attack_first_target_if_available(battle_list_region):
            ok, _ = execute_first_battle_target_attack()
            return bool(ok)
        time.sleep(0.05)

    return False


def _battle_attack_key(region):
    snapshot = build_battle_snapshot_from_region(region)
    if snapshot is None:
        return None
    return tuple((row.index, row.bounds) for row in snapshot.rows[:3])


def _log_battle_change(region):
    global battle_last_detected_names
    names = _extract_battle_creature_names(region)
    if not names:
        names = battle_last_detected_names

    if names:
        print(f"[battle-monitor] criaturas na área: {', '.join(names)}")
        battle_last_detected_names = names
        return

    selected = has_selected_target_in_region(region)
    snapshot = build_battle_snapshot_from_region(region)
    visible_count = len(snapshot.rows) if snapshot is not None else 0
    print(f"[battle-monitor] área alterada: {visible_count} linhas visíveis, selecionado={selected}")
    battle_last_detected_names = ()


def monitor_battle_region():
    global battle_monitor_active, battle_monitor_job, battle_last_region_signature, battle_last_change_log_at, battle_last_scan_at

    if not battle_monitor_active or battle_list_region is None or appController._training is None:
        battle_monitor_active = False
        return

    now = time.monotonic()
    if battle_last_scan_at and (now - battle_last_scan_at) < battle_scan_interval_seconds:
        if globals().get("root") is not None and battle_monitor_active:
            battle_monitor_job = root.after(int(battle_scan_interval_seconds * 1000), monitor_battle_region)
        return

    battle_last_scan_at = now
    entities = _get_battle_entities(battle_list_region)
    count = len(entities)
    selected = has_selected_target_in_region(battle_list_region)
    
    if count > 1 and selected:
        print(f"[battle-monitor] tem {count} bichos, atacando.")
    elif count > 0:
        names = _extract_battle_creature_names(battle_list_region)
        target_name = names[0] if names else "desconhecido"
        print(f"[battle-monitor] tem {count} bichos, novo target = {target_name}")

    if tick_training_attack():
        print("[battle-monitor] ataque executado durante o monitoramento da battle.")

    if globals().get("root") is not None and battle_monitor_active:
        battle_monitor_job = root.after(int(battle_scan_interval_seconds * 1000), monitor_battle_region)


def start_battle_monitor():
    global battle_monitor_active, battle_monitor_job, battle_last_region_signature, battle_last_change_log_at, battle_last_scan_at
    if battle_list_region is None:
        print("[battle-monitor] selecione a região da battle list antes de iniciar o monitoramento.")
        return
    battle_monitor_active = True
    battle_last_region_signature = None
    battle_last_detected_names = ()
    battle_last_change_log_at = 0.0
    battle_last_scan_at = 0.0
    if globals().get("root") is not None and battle_monitor_job is None:
        battle_monitor_job = root.after(int(battle_scan_interval_seconds * 1000), monitor_battle_region)
    else:
        print("[battle-monitor] monitor da battle iniciado.")


def stop_battle_monitor():
    global battle_monitor_active, battle_monitor_job, battle_last_change_log_at, battle_last_scan_at
    battle_monitor_active = False
    if globals().get("root") is not None and battle_monitor_job is not None:
        root.after_cancel(battle_monitor_job)
    battle_monitor_job = None
    battle_last_change_log_at = 0.0
    battle_last_scan_at = 0.0
    print("[battle-monitor] monitor da battle parado.")


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
                returnBox.insert("1.0", f"Não foi possível inicializar o controlador Windows: {exc}\n")
                return
            if not appController._actionManager.is_valid():
                appController._actionManager = None
                returnBox.delete("1.0", tk.END)
                returnBox.insert("1.0", f"A janela selecionada não está ativa ou não é válida. Selecione outra janela.\n")
                start_btn.configure(state=tk.DISABLED)
                busca_varinha_btn.configure(state=tk.DISABLED)
                busca_water_btn.configure(state=tk.DISABLED)
                return
            returnBox.delete("1.0", tk.END)
            returnBox.insert("1.0", f"Selected window: {title}\nHWND: {hwnd}\n")
            start_btn.configure(state=tk.NORMAL)
            busca_varinha_btn.configure(state=tk.NORMAL)
            busca_water_btn.configure(state=tk.NORMAL)
        else:
            returnBox.delete("1.0", tk.END)
            returnBox.insert("1.0", "Selected window not found in list.\n")
    except Exception as e:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"Error selecting window: {str(e)}\n")


def search_runa():
    ok, message = _require_action_manager("capturar a runa")
    if not ok:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"{message}\n")
        return
    if not appController._rune:
        appController._rune = _load_runa(appController._actionManager)
    returnBox.delete("1.0", tk.END)

    hotkey_name = normalize_hotkey(key.get())
    if not hotkey_name:
        returnBox.insert("1.0", "Informe uma hotkey antes de capturar a runa.\n")
        return

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.getRuna(key_name=hotkey_name)
        key_entry.delete(0, tk.END)
    out = buf.getvalue()
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


def load_runa():
    if not appController._rune:
        appController._rune = _load_runa(appController._actionManager)
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.load_mappings()
    out = buf.getvalue()
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


def save_runa():
    if not appController._rune:
        appController._rune = _load_runa(appController._actionManager)
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.save_mappings()
    out = buf.getvalue()
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


def list_runa():
    if not appController._rune:
        appController._rune = _load_runa(appController._actionManager)
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.list_mappings()
    out = buf.getvalue()
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


def reset_runa():
    if not appController._rune:
        appController._rune = _load_runa(appController._actionManager)
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.resetRuna(key_name=normalize_hotkey(key.get()))
        key_entry.delete(0, tk.END)
    out = buf.getvalue()
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


def start_macro_rune():
    ok, message = _require_action_manager("iniciar a macro")
    if not ok:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"{message}\n")
        return
    if not appController._rune:
        appController._rune = _load_runa(appController._actionManager)
    appController._rune.Atacar(True)
    macro_rune_start_btn.config(state=tk.DISABLED)
    macro_rune_stop_btn.config(state=tk.NORMAL)


def stop_macro_rune():
    if not appController._rune:
        appController._rune = _load_runa(appController._actionManager)
    try:
        appController._rune.Atacar(False)
    except Exception:
        macro_rune_start_btn.config(state=tk.NORMAL)
        macro_rune_stop_btn.config(state=tk.DISABLED)
        return

    macro_rune_start_btn.config(state=tk.NORMAL)
    macro_rune_stop_btn.config(state=tk.DISABLED)


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
    out = buf.getvalue()
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


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
    out = buf.getvalue()
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


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
    out = buf.getvalue()
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)


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
        returnBox.insert("1.0", "Necessário definir a varinha de pesca antes de iniciar.\n")
        return
    if not appController._fishing.watersCoords:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Necessário definir ao menos uma água antes de iniciar.\n")
        return

    started = appController._fishing.Pescar()
    start_btn.config(state=tk.DISABLED if started else tk.NORMAL)
    stop_btn.config(state=tk.NORMAL if started else tk.DISABLED)


def stop_pesca():
    if not appController._fishing:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Bot de pesca não está inicializado.\n")
        return

    appController._fishing.Pescar()
    start_btn.config(state=tk.NORMAL)
    stop_btn.config(state=tk.DISABLED)
    returnBox.delete("1.0", tk.END)
    returnBox.insert("1.0", "Pesca parada.\n")



def _get_battle_entities(region):
    """
    Detecta as linhas de criaturas na Battle List por suas barras de vida.

    Melhorias:
    - Detecta tons variados de verde e vermelho.
    - Usa a extensão horizontal da barra, não apenas a soma de pixels.
    - Agrupa pixels próximos verticalmente.
    - Evita juntar duas barras que estejam em linhas diferentes.
    - Retorna uma bounding box para cada criatura detectada.
    """
    if ImageGrab is None or region is None or np is None:
        return []

    try:
        image = ImageGrab.grab(bbox=region.as_tuple()).convert("RGB")
        arr = np.asarray(image, dtype=np.uint8)
    except Exception as exc:
        print(f"[battle-detect] erro na captura: {exc}")
        return []

    height, width = arr.shape[:2]

    if height < 5 or width < 10:
        return []

    # Remove o cabeçalho da Battle List.
    start_y = min(25, height // 4)
    play_area = arr[start_y:, :, :]

    if play_area.size == 0:
        return []

    R = play_area[:, :, 0].astype(np.int16)
    G = play_area[:, :, 1].astype(np.int16)
    B = play_area[:, :, 2].astype(np.int16)

    # Barras verdes: aceita diferentes tons de verde.
    green_bar = (
        (G >= 65)
        & (G > R * 1.20)
        & (G > B * 1.15)
        & (R < 155)
        & (B < 155)
    )

    # Barras vermelhas: inclui a barra de um alvo selecionado.
    red_bar = (
        (R >= 100)
        & (R > G * 1.25)
        & (R > B * 1.20)
        & (G < 155)
    )

    bar_mask = green_bar | red_bar

    # Exige uma quantidade mínima de pixels coloridos por linha.
    min_pixels = max(8, int(width * 0.04))
    min_span = max(12, int(width * 0.06))

    active_rows = []

    for y in range(bar_mask.shape[0]):
        xs = np.flatnonzero(bar_mask[y])

        if len(xs) < min_pixels:
            continue

        # Uma barra precisa ocupar uma extensão horizontal razoável.
        if int(xs[-1]) - int(xs[0]) + 1 < min_span:
            continue

        active_rows.append(y)

    if not active_rows:
        print("[battle-detect] nenhuma barra de vida detectada.")
        return []

    # Agrupa as linhas pertencentes à mesma barra.
    # Pequenos intervalos entre pixels são tolerados.
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

    # Converte os blocos detectados em regiões clicáveis.
    bounds = []

    for top, bottom in blocks:
        bar_height = bottom - top + 1

        # Descarta ruídos de apenas um pixel.
        if bar_height < 2:
            continue

        # A barra de vida fica abaixo do nome da criatura.
        row_top = region.top + start_y + top - 13
        row_bottom = region.top + start_y + bottom + 3

        # Mantém os limites dentro da região selecionada.
        row_top = max(region.top, row_top)
        row_bottom = min(region.bottom, row_bottom)

        if row_bottom <= row_top:
            continue

        bounds.append(
            (
                region.left,
                row_top,
                region.right,
                row_bottom,
            )
        )

    # Ordena as criaturas de cima para baixo.
    bounds.sort(key=lambda item: item[1])

    # Remove caixas verticais praticamente duplicadas.
    unique_bounds = []

    for item in bounds:
        center_y = (item[1] + item[3]) // 2

        duplicate = any(
            abs(center_y - ((old[1] + old[3]) // 2)) <= 4
            for old in unique_bounds
        )

        if not duplicate:
            unique_bounds.append(item)

    print(
        f"[battle-detect] barras detectadas: {len(unique_bounds)}"
    )

    return unique_bounds[:20]


def _count_real_battle_targets(region):
    entities = _get_battle_entities(region)
    return len(entities) if entities else 0


def build_battle_snapshot_from_region(region):
    if region is None:
        return None

    bounds_list = _get_battle_entities(region)
    
    if not bounds_list:
        return BattleListSnapshot(
            rows=(),
            state=SelectorState.UNCERTAIN,
            complete=False,
            captured_at=time.time(),
        )

    rows = []
    # Limita a 5 alvos por segurança, mas suporta quantos aparecerem na tela
    for index, (l, t, r, b) in enumerate(bounds_list[:5]):
        rows.append(
            BattleListRow(
                index=index,
                bounds=(l, t, r, b),
                confidence=0.98,
            )
        )

    return BattleListSnapshot(
        rows=tuple(rows),
        state=SelectorState.VALID,
        complete=True,
        captured_at=time.time(),
    )


def get_first_battle_target_position(region, snapshot):
    if region is None or snapshot is None or not snapshot.rows:
        return None
    # Pega a posição central do PRIMEIRO alvo detectado
    row = snapshot.rows[0]
    l, t, r, b = row.bounds
    x = (l + r) // 2
    y = (t + b) // 2
    return (x, y)


def has_selected_target_in_region(region):
    if ImageGrab is None or region is None:
        return False

    try:
        image = ImageGrab.grab(bbox=region.as_tuple())
        rgb = image.convert("RGB")
        width, height = rgb.size
        red_pixel_count = 0
        total_pixels = width * height

        for y in range(height):
            for x in range(width):
                r, g, b = rgb.getpixel((x, y))
                if r > 160 and g < 120 and b < 120:
                    red_pixel_count += 1

        if total_pixels == 0:
            return False

        return (red_pixel_count / total_pixels) > 0.002
    except Exception:
        return False


def should_attack_first_target_if_available(region):
    global battle_last_attack_at, battle_last_attack_key
    if region is None:
        return False
    if has_selected_target_in_region(region):
        return False

    snapshot = build_battle_snapshot_from_region(region)
    if snapshot is None or not snapshot.complete:
        return False

    # REGRA ESTRITA: precisa de 2+ linhas para atacar.
    if len(snapshot.rows) <= 1:
        return False

    selector = SafeBattleListTargetSelector(min_confidence=0.8, required_stable_captures=1)
    eligible = selector.get_eligible_targets(snapshot)
    if not eligible:
        return False

    current_key = tuple((row.index, row.bounds) for row in snapshot.rows[:3])
    now = time.monotonic()
    if current_key == battle_last_attack_key and (now - battle_last_attack_at) < 1.2:
        return False

    return True


def execute_first_battle_target_attack():
    global battle_last_attack_at, battle_last_attack_key
    if appController._actionManager is None:
        return False, "Selecione uma janela antes de atacar o battle."
    if battle_list_region is None:
        return False, "Selecione a região da battle list antes de atacar."

    if not should_attack_first_target_if_available(battle_list_region):
        return False, "Sem alvo disponível: é preciso mais de um alvo visível e sem seleção."

    # Re-validação imediata
    snapshot = build_battle_snapshot_from_region(battle_list_region)
    if snapshot is None or not snapshot.complete or len(snapshot.rows) <= 1:
        return False, "Apenas um alvo visível no momento do clique — ataque cancelado."

    selector = SafeBattleListTargetSelector(min_confidence=0.8, required_stable_captures=1)
    eligible = selector.get_eligible_targets(snapshot)
    if len(eligible) < 1:
        return False, "Battle list sem alvos elegíveis para ataque seguro."

    target = get_first_battle_target_position(battle_list_region, snapshot)
    if target is None:
        return False, "Não foi possível localizar o alvo do battle."

    battle_last_attack_at = time.monotonic()
    battle_last_attack_key = tuple((row.index, row.bounds) for row in snapshot.rows[:3])

    appController._actionManager.focusWindow()
    appController._actionManager.move_mouse(target)
    appController._actionManager.left_click(target)
    return True, f"Atacando primeiro alvo em {target}."


def start_treino():
    if not appController._training:
        appController._training = TrainingStateMachine()

    appController._training.start()
    start_battle_monitor()

    snapshot = build_battle_snapshot_from_region(battle_list_region)
    if snapshot is None:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Treinamento aguardando região da battle list.\n")
        return

    if len(snapshot.rows) < 2:
        decision = appController._training.evaluate_battle_list(snapshot)
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"Treinamento aguardando região válida.\nEstado: {appController._training.state.value}\nMotivo: {decision.reason}\n")
        return

    if appController._training.selector.validate_snapshot(snapshot):
        appController._training.train()
        next_target = appController._training.get_next_target(snapshot)
        decision = appController._training.evaluate_battle_list(snapshot)
        ok, message = execute_first_battle_target_attack()
        returnBox.delete("1.0", tk.END)
        returnBox.insert(
            "1.0",
            f"Treinamento ativo.\nEstado: {appController._training.state.value}\n"
            f"Região: {battle_list_region.left},{battle_list_region.top},{battle_list_region.width},{battle_list_region.height}\n"
            f"Próximo alvo seguro: {next_target}\n"
            f"Alvos elegíveis: {decision.eligible_targets}\nProtegido: {decision.protected_index}\n"
            f"Ação: {'ok' if ok else 'bloqueada'}\nDetalhe: {message}\n"
            "Regra: só ataca o primeiro alvo quando há pelo menos mais um target na battle.\n"
        )
        return

    decision = appController._training.evaluate_battle_list(snapshot)
    returnBox.delete("1.0", tk.END)
    returnBox.insert("1.0", f"Treinamento aguardando estabilidade.\nEstado: {appController._training.state.value}\nMotivo: {decision.reason}\n")


def stop_treino():
    if not appController._training:
        appController._training = TrainingStateMachine()
    stop_battle_monitor()
    appController._training.pause()
    returnBox.delete("1.0", tk.END)
    returnBox.insert("1.0", f"Treinamento pausado.\nEstado: {appController._training.state.value}\n")


def configure_battle_list_region(region):
    global battle_list_region, battle_list_validator
    if region is None:
        return
    screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
    battle_list_validator = BattleListRegionValidator(screen_size=(screen_width, screen_height))
    battle_list_region = region
    if battle_list_validator.is_valid(region):
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"Região da Battle List validada.\nMonitor: {region.monitor}\nX: {region.left} Y: {region.top} L: {region.width} A: {region.height}\n")
    else:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Região inválida. Ajuste a seleção da Battle List.\n")


def preview_battle_list_capture():
    global battle_list_region
    if ImageGrab is None:
        returnBox.insert("1.0", "Pillow não está disponível para pré-visualização da captura.\n")
        return
    if battle_list_region is None or not battle_list_validator.is_valid(battle_list_region):
        returnBox.insert("1.0", "Selecione primeiro uma região válida da Battle List.\n")
        return

    preview = tk.Toplevel(root)
    preview.title("Prévia da Battle List")
    preview.attributes("-topmost", True)
    image = ImageGrab.grab(bbox=battle_list_region.as_tuple())
    photo = ImageTk.PhotoImage(image)
    label = tk.Label(preview, image=photo)
    label.image = photo
    label.grid(padx=12, pady=12)
    preview.transient(root)
    preview.grab_set()


def select_battle_list_region():
    if ImageGrab is None or ImageTk is None:
        returnBox.insert("1.0", "Captura de tela indisponível neste ambiente.\n")
        return

    screen = ImageGrab.grab()
    full_width, full_height = screen.size
    overlay = tk.Toplevel(root)
    overlay.attributes("-topmost", True)
    overlay.geometry(f"{full_width}x{full_height}+0+0")
    overlay.overrideredirect(True)
    overlay.wm_attributes("-alpha", 0.28)

    canvas = tk.Canvas(overlay, width=full_width, height=full_height, cursor="crosshair", bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    photo = ImageTk.PhotoImage(screen)
    canvas.create_image(0, 0, image=photo, anchor="nw")
    selection_id = None
    start_x = start_y = None

    def start_selection(event):
        nonlocal selection_id, start_x, start_y
        start_x, start_y = event.x, event.y
        if selection_id is not None:
            canvas.delete(selection_id)
        selection_id = canvas.create_rectangle(start_x, start_y, event.x, event.y, outline="#77dd77", width=2)

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

        left = min(start_x, event.x)
        top = min(start_y, event.y)
        width = abs(event.x - start_x)
        height = abs(event.y - start_y)
        selection = BattleListRegion(left=left, top=top, width=max(width, 1), height=max(height, 1), monitor=1)
        configure_battle_list_region(selection)
        overlay.destroy()

    canvas.bind("<ButtonPress-1>", start_selection)
    canvas.bind("<B1-Motion>", draw_rectangle)
    canvas.bind("<ButtonRelease-1>", finish_selection)
    overlay.bind("<Escape>", lambda event: overlay.destroy())
    overlay.focus_force()


def build_ui():
    global root, combo, returnBox, key, key_entry, sobrepor_btn
    global macro_rune_start_btn, macro_rune_stop_btn
    global start_btn, stop_btn, busca_varinha_btn, busca_water_btn

    root = tk.Tk()
    root.title("Exordion 7.4 Pro")
    root.geometry("600x400")
    root.minsize(560, 360)
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
    style.configure(
        "Compact.TCombobox",
        fieldbackground="#20252b",
        background="#414954",
        foreground=FG,
        arrowcolor=FG,
        padding=2,
    )
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
    tk.Label(header, text="Exordion 7.4 Pro", bg=BG, fg=FG, font=("Segoe UI", 15, "bold")).grid(row=0, column=0, sticky="w")
    tk.Label(header, text="● Pronto", bg=BG, fg="#9af0c5", font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="e")

    content = tk.Frame(root, bg=BG)
    content.grid(row=1, column=0, sticky="ew", padx=6)
    content.columnconfigure(0, weight=1, uniform="columns")
    content.columnconfigure(1, weight=1, uniform="columns")

    def make_panel(parent, title, row, column):
        panel = tk.Frame(parent, bg=PANEL, bd=0, padx=7, pady=6, highlightthickness=1, highlightbackground=BORDER)
        panel.grid(row=row, column=column, sticky="nsew", padx=3, pady=3)
        panel.columnconfigure(0, weight=1)
        tk.Label(panel, text=title.upper(), bg=PANEL, fg=FG, font=("Segoe UI", 8, "bold"), anchor="w").grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))
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
        return tk.Button(parent, text=text, command=command, state=state, bg=fill, fg=foreground, activebackground=active, activeforeground=FG, disabledforeground=disabled_foreground, bd=0, relief="flat", highlightthickness=0, font=("Segoe UI", 7, "bold"), padx=3, pady=4, wraplength=145, cursor="hand2")

    panel_window = make_panel(content, "Selecionar janela", 0, 0)
    combo = ttk.Combobox(panel_window, state="readonly", style="Compact.TCombobox", width=22)
    combo.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 4))
    make_button(panel_window, "Listar janelas", get_windows).grid(row=2, column=0, sticky="ew", padx=(0, 2))
    make_button(panel_window, "Selecionar", select_window).grid(row=2, column=1, sticky="ew", padx=(2, 0))

    panel_training = make_panel(content, "Controles de treino", 0, 1)
    panel_training.columnconfigure(0, weight=1)
    panel_training.columnconfigure(1, weight=1)
    make_button(panel_training, "Iniciar treino", start_treino, "primary").grid(row=1, column=0, sticky="ew", padx=(0, 2), pady=(0, 3))
    make_button(panel_training, "Parar treino", stop_treino, "warning").grid(row=1, column=1, sticky="ew", padx=(2, 0), pady=(0, 3))
    make_button(panel_training, "Selecionar região Battle List", select_battle_list_region, "dark").grid(row=2, column=0, sticky="ew", padx=(0, 2))
    sobrepor_btn = make_button(panel_training, "Sobrepor: OFF", sobrepor_todas_janelas, "secondary")
    sobrepor_btn.grid(row=2, column=1, sticky="ew", padx=(2, 0))
    make_button(panel_training, "Testar captura", preview_battle_list_capture).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(3, 0))

    panel_fishing = make_panel(content, "Controles de pesca", 1, 0)
    for col in range(2):
        panel_fishing.columnconfigure(col, weight=1, uniform="fishing")
    varinha_btn = make_button(panel_fishing, "Capturar varinha", search_varinha)
    varinha_btn.grid(row=1, column=0, sticky="ew", padx=(0, 2), pady=(0, 3))
    aguas_btn = make_button(panel_fishing, "Capturar águas", search_aguas)
    aguas_btn.grid(row=1, column=1, sticky="ew", padx=(2, 0), pady=(0, 3))
    start_pesca_btn = make_button(panel_fishing, "Iniciar pesca", start_pesca, "primary")
    start_pesca_btn.grid(row=2, column=0, sticky="ew", padx=(0, 2))
    stop_pesca_btn = make_button(panel_fishing, "Parar pesca", stop_pesca, "danger")
    stop_pesca_btn.grid(row=2, column=1, sticky="ew", padx=(2, 0))
    make_button(panel_fishing, "Resetar pesca", reset_coordinates).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(3, 0))

    panel_macros = make_panel(content, "Presets e macros", 1, 1)
    for col in range(3):
        panel_macros.columnconfigure(col, weight=1, uniform="macros")
    make_button(panel_macros, "Carregar", load_runa).grid(row=1, column=0, sticky="ew", padx=(0, 2), pady=(0, 3))
    make_button(panel_macros, "Salvar", save_runa).grid(row=1, column=1, sticky="ew", padx=2, pady=(0, 3))
    make_button(panel_macros, "Listar", list_runa).grid(row=1, column=2, sticky="ew", padx=(2, 0), pady=(0, 3))
    make_button(panel_macros, "Capturar runa", search_runa).grid(row=2, column=0, sticky="ew", padx=(0, 2), pady=(0, 3))
    start_macro_btn = make_button(panel_macros, "Iniciar macro", start_macro_rune, "primary")
    start_macro_btn.grid(row=2, column=1, sticky="ew", padx=(2, 2), pady=(0, 3))
    stop_macro_btn = make_button(panel_macros, "Parar macro", stop_macro_rune, "danger")
    stop_macro_btn.grid(row=2, column=2, sticky="ew", padx=(2, 0), pady=(0, 3))
    make_button(panel_macros, "Resetar runas", reset_runa).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(3, 0))

    hotkey_frame = tk.Frame(root, bg=BG)
    hotkey_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 3))
    tk.Label(hotkey_frame, text="Hotkey", bg=BG, fg=MUTED, font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", padx=(0, 7))
    key = StringVar(value="F5")
    key_entry = tk.Entry(hotkey_frame, textvariable=key, width=8, bg="#20252b", fg=FG, insertbackground=FG, relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor="#82aaff", font=("Consolas", 8))
    key_entry.grid(row=0, column=1, sticky="w")
    key_entry.bind("<KeyRelease>", lambda event: key.set(normalize_hotkey(key.get())))

    root.bind_all("<Escape>", handle_escape)
    _install_global_esc_listener()

    def _on_close():
        _uninstall_global_esc_listener()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)

    console = tk.Frame(root, bg="#20252b", highlightbackground=BORDER, highlightthickness=1)
    console.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 8))
    console.columnconfigure(0, weight=1)
    console.rowconfigure(1, weight=1)
    tk.Label(console, text="CONSOLE", bg="#20252b", fg=MUTED, font=("Segoe UI", 8, "bold"), anchor="w").grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 1))
    returnBox = tk.Text(console, bg="#20252b", fg=FG, insertbackground=FG, selectbackground="#526b82", selectforeground=FG, relief="flat", height=4, font=("Consolas", 8), wrap="word", padx=6, pady=4, borderwidth=0)
    returnBox.grid(row=1, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(console, orient="vertical", command=returnBox.yview)
    scrollbar.grid(row=1, column=1, sticky="ns")
    returnBox.configure(yscrollcommand=scrollbar.set)
    returnBox.insert("1.0", "Exordion 7.4 Pro pronto. Selecione uma janela para começar.\n")

    start_btn = start_pesca_btn
    stop_btn = stop_pesca_btn
    busca_varinha_btn = varinha_btn
    busca_water_btn = aguas_btn
    macro_rune_start_btn = start_macro_btn
    macro_rune_stop_btn = stop_macro_btn

    root.update_idletasks()
    width, height = 600, 400
    x = max(0, (root.winfo_screenwidth() - width) // 2)
    y = max(0, (root.winfo_screenheight() - height) // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")
    root.mainloop()


def run_demo():
    print("Exordion 7.4 Pro - modo de demonstração")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Exordion 7.4 Pro")
    parser.add_argument("--demo", action="store_true", help="executa a versão em modo console")
    parser.add_argument("--gui", action="store_true", help="força a interface gráfica")
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
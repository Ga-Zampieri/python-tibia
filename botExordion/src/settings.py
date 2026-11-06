"""Perfis em JSON: tudo que é configurado fica salvo por personagem."""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
LEGACY_MAPPINGS = ROOT / "assets" / "runa_mappings.json"
DEFAULT_NAME = "Padrão"

DEFAULT_PROFILE = {
    "window_title": "",
    # Mapeamentos antigos guardavam posição na tela; convertidos ao achar a janela.
    "legacy_screen_coords": False,
    "player_position": None,
    # tecla -> {"mode": "normal"|"self"|"drag", "pos": [x, y], "end": [x, y]|None}
    "macros": {},
    "drag_in_background": True,
    "training": {"mode": "summon", "region": None, "allowed_names": []},
    "fishing": {"rod": None, "waters": []},
    "repeater": {"key": "f5", "interval": 1.0},
    "alarm": {"sound": True, "pause_modules": True},
    "survival": {
        "hp_bar": None,
        "mana_bar": None,
        "eat": {"enabled": False, "pos": None, "interval": 180},
        "anti_idle": {"enabled": False, "interval": 300},
        "rules": [
            {"enabled": False, "stat": "hp", "op": "<", "percent": 50, "action": "", "cooldown": 1.0},
            {"enabled": False, "stat": "hp", "op": "<", "percent": 30, "action": "", "cooldown": 1.0},
            {"enabled": False, "stat": "mana", "op": ">", "percent": 90, "action": "", "cooldown": 2.0},
        ],
    },
    "rune_maker": {
        "blank": None,
        "hand": None,
        "output": None,
        "spell": "",
        "mana_percent": 80,
        "interval": 60,
        "cast_wait": 1.5,
    },
}


def merge_defaults(defaults: dict, data: dict) -> dict:
    merged = copy.deepcopy(defaults)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict) and merged[key]:
            merged[key] = merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def import_legacy_mappings(data: dict) -> dict:
    """Converte o antigo runa_mappings.json para um perfil."""
    profile = copy.deepcopy(DEFAULT_PROFILE)
    profile["legacy_screen_coords"] = True
    mappings = data["mappings"] if isinstance(data.get("mappings"), dict) else data
    profile["player_position"] = data.get("player_position")
    for key, value in mappings.items():
        if not isinstance(value, dict):
            profile["macros"][key] = {"mode": "normal", "pos": list(value), "end": None}
            continue
        if value.get("rune") is None:
            continue
        if value.get("self_use"):
            mode = "self"
        elif value.get("push_item"):
            mode = "drag"
        else:
            mode = "normal"
        profile["macros"][key] = {"mode": mode, "pos": list(value["rune"]), "end": value.get("drag_end")}
        if value.get("player") and not profile["player_position"]:
            profile["player_position"] = list(value["player"])
    return profile


class ProfileStore:
    def __init__(self, base_dir: Path = CONFIG_DIR, legacy_file: Path = LEGACY_MAPPINGS):
        self.dir = Path(base_dir) / "profiles"
        self.state_file = Path(base_dir) / "app.json"
        self.legacy_file = Path(legacy_file)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, name: str) -> Path:
        safe = re.sub(r'[<>:"/\\|?*]', "_", name).strip() or DEFAULT_NAME
        return self.dir / f"{safe}.json"

    def names(self) -> list:
        return sorted(path.stem for path in self.dir.glob("*.json"))

    def load(self, name: str) -> dict:
        path = self._path(name)
        try:
            return merge_defaults(DEFAULT_PROFILE, json.loads(path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return copy.deepcopy(DEFAULT_PROFILE)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Perfil %s ilegível (%s); guardado como .bad", path.name, exc)
            os.replace(path, path.with_suffix(".bad"))
            return copy.deepcopy(DEFAULT_PROFILE)

    def save(self, name: str, profile: dict) -> None:
        path = self._path(name)
        temp = path.with_suffix(".tmp")
        with self._lock:
            temp.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temp, path)

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)

    def remember_last(self, name: str) -> None:
        self.state_file.write_text(json.dumps({"last_profile": name}, ensure_ascii=False), encoding="utf-8")

    def load_last(self):
        """Perfil da última sessão; na primeira vez, importa os mapeamentos antigos."""
        if not self.names():
            profile = copy.deepcopy(DEFAULT_PROFILE)
            if self.legacy_file.exists():
                try:
                    profile = import_legacy_mappings(json.loads(self.legacy_file.read_text(encoding="utf-8")))
                except Exception:
                    logger.exception("Não foi possível importar %s", self.legacy_file)
            self.save(DEFAULT_NAME, profile)
            return DEFAULT_NAME, profile
        try:
            last = json.loads(self.state_file.read_text(encoding="utf-8")).get("last_profile")
        except (OSError, json.JSONDecodeError):
            last = None
        name = last if last in self.names() else self.names()[0]
        return name, self.load(name)

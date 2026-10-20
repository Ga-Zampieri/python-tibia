from __future__ import annotations

from typing import Any, Dict, List


class HotkeyManager:
    def __init__(self) -> None:
        self.hotkeys: Dict[str, Dict[str, Any]] = {}

    def register(self, name: str, combo: str, action: Any) -> None:
        self.hotkeys[name] = {"combo": combo, "action": action, "enabled": True}

    def unregister(self, name: str) -> None:
        self.hotkeys.pop(name, None)

    def enable(self, name: str) -> None:
        if name in self.hotkeys:
            self.hotkeys[name]["enabled"] = True

    def disable(self, name: str) -> None:
        if name in self.hotkeys:
            self.hotkeys[name]["enabled"] = False

    def is_conflict(self, combo: str) -> bool:
        return any(entry["combo"] == combo and entry["enabled"] for entry in self.hotkeys.values())

    def list_hotkeys(self) -> List[str]:
        return list(self.hotkeys)

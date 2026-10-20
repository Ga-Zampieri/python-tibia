from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List


class SQLiteProfileStore:
    """Simple SQLite store for profiles and configuration data."""

    def __init__(self, db_path: str = "config/profiles.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def save_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        payload = json.dumps(profile, ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO profiles (name, payload) VALUES (?, ?)",
                (profile.get("name", "profile"), payload),
            )
            profile["id"] = cursor.lastrowid
        return profile

    def list_profiles(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, name, payload FROM profiles ORDER BY id DESC"
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            profile_id, name, payload = row
            data = json.loads(payload)
            data["id"] = profile_id
            data["name"] = name
            result.append(data)
        return result

    def export_profile(self, profile_name: str, path: str) -> str:
        profile = next((p for p in self.list_profiles() if p.get("name") == profile_name), None)
        if profile is None:
            raise ValueError(f"Profile {profile_name!r} not found")
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(destination)

    def import_profile(self, path: str) -> Dict[str, Any]:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return self.save_profile(data)

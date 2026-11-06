from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Tuple


class SelectorState(Enum):
    INITIALIZING = "initializing"
    VALID = "valid"
    UNCERTAIN = "uncertain"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class BattleListRow:
    index: int
    bounds: Tuple[int, int, int, int]
    confidence: float
    # "green" | "yellow" | "red" | "unknown"
    hp_state: str = "unknown"
    # Forma do nome na lista; `allowed` é False se não está na lista de permitidos.
    signature: str = ""
    allowed: bool = True


@dataclass(frozen=True)
class BattleListRegion:
    left: int
    top: int
    width: int
    height: int
    monitor: int = 1

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def as_tuple(self) -> Tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)


class BattleListRegionValidator:
    """Valida regiões da Battle List usando os limites do desktop virtual (multi-monitor)."""

    def __init__(
        self,
        screen_size: Optional[Tuple[int, int]] = None,
        screen_bounds: Optional[Tuple[int, int, int, int]] = None,
        min_width: int = 80,
        min_height: int = 60,
    ):
        if screen_bounds is not None:
            self.bounds: Tuple[int, int, int, int] = tuple(int(v) for v in screen_bounds)
        elif screen_size is not None:
            self.bounds = (0, 0, int(screen_size[0]), int(screen_size[1]))
        else:
            self.bounds = (0, 0, 1920, 1080)

        self.min_width = max(1, int(min_width))
        self.min_height = max(1, int(min_height))

    @property
    def screen_size(self) -> Tuple[int, int]:
        return (self.bounds[2], self.bounds[3])

    def is_valid(self, region: BattleListRegion) -> bool:
        if region.monitor < 1:
            return False
        if region.width < self.min_width or region.height < self.min_height:
            return False

        vleft, vtop, vwidth, vheight = self.bounds
        vright = vleft + vwidth
        vbottom = vtop + vheight

        if region.left < vleft or region.top < vtop:
            return False
        if region.right > vright or region.bottom > vbottom:
            return False
        return True


@dataclass(frozen=True)
class BattleListSnapshot:
    rows: Tuple[BattleListRow, ...]
    state: SelectorState
    complete: bool
    captured_at: float
    selected_index: Optional[int] = None  # índice da linha atacada, ou None


class SafeBattleListTargetSelector:
    """Selector com regra de proteção da última linha (modo Summon)."""

    def __init__(self, min_confidence: float = 0.98, required_stable_captures: int = 2):
        self.min_confidence = min_confidence
        self.required_stable_captures = max(1, int(required_stable_captures))
        self.last_valid_snapshot: Optional[BattleListSnapshot] = None
        self._stable_capture_count = 0

    def _snapshot_meets_base_rules(self, snapshot: BattleListSnapshot) -> bool:
        if snapshot.state is not SelectorState.VALID:
            return False
        if not snapshot.complete:
            return False
        if not snapshot.rows:
            return False
        if any(row.confidence < self.min_confidence for row in snapshot.rows):
            return False
        return True

    def validate_snapshot(self, snapshot: BattleListSnapshot) -> bool:
        if not self._snapshot_meets_base_rules(snapshot):
            return False

        if self.last_valid_snapshot is None:
            self.last_valid_snapshot = snapshot
            self._stable_capture_count = 1
            return self._stable_capture_count >= self.required_stable_captures

        if self._same_rows(self.last_valid_snapshot.rows, snapshot.rows):
            self._stable_capture_count += 1
        else:
            self._stable_capture_count = 1
            self.last_valid_snapshot = snapshot
            return False

        self.last_valid_snapshot = snapshot
        return self._stable_capture_count >= self.required_stable_captures

    def _same_rows(self, left: Sequence[BattleListRow], right: Sequence[BattleListRow]) -> bool:
        if len(left) != len(right):
            return False
        for a, b in zip(left, right):
            if a.index != b.index or a.bounds != b.bounds:
                return False
        return True

    def get_protected_index(self, snapshot: BattleListSnapshot) -> Optional[int]:
        if not snapshot.rows:
            return None
        return len(snapshot.rows) - 1

    def is_candidate_eligible(self, snapshot: BattleListSnapshot, candidate_index: int) -> bool:
        if candidate_index < 0:
            return False
        if not snapshot.rows:
            return False
        if not self._snapshot_meets_base_rules(snapshot):
            return False
        if candidate_index >= len(snapshot.rows):
            return False

        protected_index = self.get_protected_index(snapshot)
        if protected_index is not None and candidate_index == protected_index:
            return False

        row = snapshot.rows[candidate_index]
        if row.confidence < self.min_confidence:
            return False

        return True

    def get_eligible_targets(self, snapshot: BattleListSnapshot) -> Tuple[int, ...]:
        if not self._snapshot_meets_base_rules(snapshot):
            return ()
        indices = []
        for idx in range(len(snapshot.rows)):
            if self.is_candidate_eligible(snapshot, idx):
                indices.append(idx)
        return tuple(indices)

    def reset(self) -> None:
        self.last_valid_snapshot = None
        self._stable_capture_count = 0
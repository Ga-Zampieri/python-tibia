from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Tuple

Point = Tuple[int, int]


@dataclass
class CoordinateTransform:
    """Transforms logical coordinates to screen/window coordinates.

    The project intentionally keeps a logical coordinate model independent from the
    physical cursor, and all conversions remain consistent for different desktop
    scales and window positions.
    """

    window_rect: Iterable[int] = (0, 0, 1920, 1080)
    dpi_scale: float = 1.0
    screen_size: Tuple[int, int] = (1920, 1080)

    def __post_init__(self) -> None:
        self.window_rect = tuple(int(v) for v in self.window_rect)
        if len(self.window_rect) != 4:
            raise ValueError("window_rect expects (left, top, width, height)")
        self.scale_factor = max(float(self.dpi_scale), 0.1)
        if not self.screen_size:
            self.screen_size = (1920, 1080)

    def _clamp(self, x: int, y: int) -> Point:
        max_x, max_y = self.screen_size
        x = max(0, min(int(x), max_x))
        y = max(0, min(int(y), max_y))
        return (x, y)

    def to_screen(self, point: Point) -> Point:
        x, y = point
        return self._clamp(x, y)

    def to_window(self, point: Point) -> Point:
        x, y = point
        left, top, _, _ = self.window_rect
        return self._clamp(x - left, y - top)

    def to_logical(self, point: Point) -> Point:
        return self.to_screen(point)

    def normalize(self, point: Point) -> Tuple[float, float]:
        x, y = point
        max_x, max_y = self.screen_size
        return (x / max_x if max_x else 0.0, y / max_y if max_y else 0.0)

    def relative_to_window(self, point: Point) -> Point:
        return self.to_window(point)

    def set_window_rect(self, rect: Iterable[int]) -> None:
        self.window_rect = tuple(int(v) for v in rect)

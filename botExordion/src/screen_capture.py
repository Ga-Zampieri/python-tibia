from __future__ import annotations

from typing import Optional, Tuple

try:
    import numpy as np
    import PIL.ImageGrab as ImageGrab
except Exception:  # pragma: no cover
    np = None
    ImageGrab = None


class ScreenCapture:
    def __init__(self, monitor: int = 1) -> None:
        self.monitor = monitor

    def capture(self, region: Optional[Tuple[int, int, int, int]] = None):
        if ImageGrab is None:
            raise RuntimeError("Pillow is required for screen capture")
        if region is None:
            return ImageGrab.grab()
        return ImageGrab.grab(bbox=region)

    def capture_array(self, region: Optional[Tuple[int, int, int, int]] = None):
        image = self.capture(region)
        if np is None:
            return image
        return np.array(image)

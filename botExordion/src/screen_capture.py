from __future__ import annotations

from typing import Optional, Tuple

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:
    import PIL.Image as Image
    import PIL.ImageGrab as ImageGrab
except Exception:  # pragma: no cover
    Image = None
    ImageGrab = None

try:
    import mss as _mss_module
except Exception:  # pragma: no cover
    _mss_module = None

_mss_instance = None


class ScreenCapture:
    """Captura de tela multi-monitor.

    Prefere `mss` (rápido, lida com desktop virtual) e cai para Pillow com
    `all_screens=True` se `mss` não estiver disponível. Coordenadas são sempre
    em pixels físicos do desktop virtual e podem ser negativas (monitor à esquerda
    ou acima do primário).
    """

    def __init__(self, monitor: int = 1) -> None:
        self.monitor = monitor

    @staticmethod
    def virtual_bounds() -> Tuple[int, int, int, int]:
        """(left, top, width, height) cobrindo todos os monitores."""
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

    def capture(self, region: Optional[Tuple[int, int, int, int]] = None):
        global _mss_instance

        if _mss_module is not None:
            try:
                if _mss_instance is None:
                    _mss_instance = _mss_module.MSS()
                if region is None:
                    vleft, vtop, vwidth, vheight = self.virtual_bounds()
                    monitor = {"left": vleft, "top": vtop,
                               "width": max(1, vwidth), "height": max(1, vheight)}
                else:
                    left, top, right, bottom = [int(v) for v in region]
                    monitor = {"left": left, "top": top,
                               "width": max(1, right - left),
                               "height": max(1, bottom - top)}
                shot = _mss_instance.grab(monitor)
                if Image is None:
                    return shot
                return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            except Exception:
                pass

        if ImageGrab is None:
            raise RuntimeError("Pillow is required for screen capture")

        try:
            return ImageGrab.grab(bbox=region, all_screens=True)
        except TypeError:
            return ImageGrab.grab(bbox=region)

    def capture_array(self, region: Optional[Tuple[int, int, int, int]] = None):
        image = self.capture(region)
        if np is None or not hasattr(image, "__array__"):
            return image
        return np.array(image)
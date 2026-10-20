import pygetwindow as gw


def getWindows(window_title: str = None):
    """Listar janelas abertas. Quando a busca for vazia, retorna todas as janelas visíveis."""
    try:
        if window_title:
            windows = gw.getWindowsWithTitle(window_title)
        else:
            windows = gw.getAllWindows()

        result = []
        for win in windows:
            try:
                title = getattr(win, "title", "") or ""
                if not title.strip():
                    continue
                hwnd = getattr(win, "_hWnd", None)
                if hwnd is None:
                    continue
                result.append((title, int(hwnd)))
            except Exception:
                continue

        result = sorted(result, key=lambda item: item[0].lower())
        print(f">>> Found {len(result)} windows")
        return result
    except Exception as Ex:
        print("From GetHWND.py: ", Ex)
        print(f">>> Window Not Located: '{window_title}'")
        return []


def selectWindow(windows_list, window_title: str):
    """Select specific window from list by title."""
    try:
        if not windows_list:
            print("No windows available to select.")
            return None

        for title, hwnd in windows_list:
            if title == window_title:
                print(f"Selected window: {title} (hwnd: {hwnd})")
                return hwnd

        print("No matching window found.")
        return None
    except Exception as Ex:
        print("From SelectWindow.py: ", Ex)
        return None

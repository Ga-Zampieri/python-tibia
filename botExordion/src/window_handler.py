import pygetwindow as gw

def getWindows(window_title: str = None):
    """
    Get all windows containing window_title in their title.
    Returns list of tuples (title, hwnd)
    """
    try:
        if not window_title:
            window_title = "Exordion V"
            
        windows = gw.getWindowsWithTitle(window_title)
        result = []
        
        for win in windows:
            try:
                hwnd = win._hWnd
                result.append((win.title, hwnd))
            except Exception:
                continue
                
        print(f">>> Found {len(result)} windows")
        return result
        
    except Exception as Ex:
        print("From GetHWND.py: ", Ex)
        print(f">>> Window Not Located: '{window_title}'")
        return []

def selectWindow(windows_list, window_title: str):
    """
    Select specific window from list by title.
    windows_list should be list of (title, hwnd) tuples from getWindows()
    """
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
import tkinter as tk
from tkinter import N, S, W, E, StringVar, ttk
import sys
import os

# Adiciona o caminho atual ao Python path para imports absolutos
if getattr(sys, 'frozen', False):
    # Se estiver executando como executável compilado
    base_path = sys._MEIPASS
else:
    # Se estiver executando como script
    base_path = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, base_path)

from action_manager import ActionManager
from overlay import create_overlay, update_overlay_buttons

class AppController:
    def __init__(self):
        self._hwnd = None
        self._actionManager = None
        self._fishing = None
        self._rune = None

windows = []

def get_windows():   
    global windows
    from window_handler import getWindows  
    returnBox.delete("1.0", tk.END)
    
    try:
        windows = getWindows(None)
        
        # Update combobox with window titles
        window_titles = [f"{title} ({hwnd})" for title, hwnd in windows] if windows else []
        combo['values'] = window_titles
        
        # Select first item if available
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
            appController._actionManager = ActionManager(hwnd)
            
            returnBox.delete("1.0", tk.END)
            returnBox.insert("1.0", f"Selected window: {title}\nHWND: {hwnd}\n")
            criar_callbacks()
            create_overlay(hwnd, appController)
        else:
            returnBox.delete("1.0", tk.END)
            returnBox.insert("1.0", "Selected window not found in list.\n")
            
    except Exception as e:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"Error selecting window: {str(e)}\n")    

def criar_callbacks():
    """Conecta as funções de callback aos módulos"""
    
    def on_runa_status_changed(new_status):
        print(f"📢 CALLBACK RUNA: Status recebido -> {new_status}")
        # Atualiza overlay
        update_overlay_buttons()
        
        returnBox.insert("1.0", f"Runas: {new_status}\n")
        returnBox.see("1.0")
    
    def on_fishing_status_changed(new_status):
        print(f"📢 CALLBACK PESCA: Status recebido -> {new_status}")

        update_overlay_buttons()
        
        returnBox.insert("1.0", f"Pesca: {new_status}\n")
        returnBox.see("1.0")
    
    # Conecta os callbacks
    if appController._rune:
        appController._rune.set_status_callback(on_runa_status_changed)
    
    if appController._fishing:
        appController._fishing.set_status_callback(on_fishing_status_changed)

root = tk.Tk()
root.title("Helper")
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)	

mainframe = ttk.Frame(root, padding=(3, 3, 12, 12))
mainframe.grid(column=0, row=0, sticky=(N, S, W, E))

window_frame = ttk.LabelFrame(mainframe, text="Window Selection", padding=(5, 5, 5, 5))
window_frame.grid(column=1, row=1, columnspan=3, sticky=(W, E))
window_frame.columnconfigure(1, weight=1)

window_select_btn = ttk.Button(window_frame, text="Get Windows", command=get_windows)
window_select_btn.grid(column=0, row=0, padx=5)

combo = ttk.Combobox(window_frame, state="readonly", width=40)
combo.grid(column=1, row=0, padx=5, sticky=(W, E))

window_select_btn = ttk.Button(window_frame, text="Select Window", command=select_window)
window_select_btn.grid(column=2, row=0, padx=5)

returnBox = tk.Text(mainframe, width=50, height=8)
returnBox.grid(column=1, row=2, columnspan=3, sticky=(W, E))


appController = AppController()
root.mainloop()


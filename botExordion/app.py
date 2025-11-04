import contextlib
import io
import tkinter as tk
import threading
from tkinter import N, S, W, E, StringVar, ttk

from .src.status import Status
from .src.action_manager import ActionManager
from .src.fishing import Pesca
from .src.macro_rune import Runa

class AppController:
    def __init__(self):
        self._hwnd = None
        self._actionManager = None
        self._fishing = None
        self._rune = None
    

sobrepor_janela = False
worker_thread = None
_worker_lock = threading.Lock()
windows = []

def sobrepor_todas_janelas():
    global sobrepor_janela
    sobrepor_janela = not sobrepor_janela
    try:
        root.attributes('-topmost', sobrepor_janela)
        if sobrepor_janela:
            sobrepor_btn.configure(background="lightgreen")
        else:
            sobrepor_btn.configure(background="lightcoral")
    except Exception:
        try:
            root.wm_attributes('-topmost', 1 if sobrepor_janela else 0)
        except Exception:
            pass


def get_windows():   
    global windows
    from .src.window_handler import getWindows
    returnBox.delete("1.0", tk.END)
    
    try:
        windows = getWindows(None)  # gets list of (title, hwnd) tuples
        
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
            
            # Enable relevant buttons after window selection
            start_btn.configure(state=tk.NORMAL)
            busca_varinha_btn.configure(state=tk.NORMAL)
            busca_water_btn.configure(state=tk.NORMAL)
            
        else:
            returnBox.delete("1.0", tk.END)
            returnBox.insert("1.0", "Selected window not found in list.\n")
            
    except Exception as e:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"Error selecting window: {str(e)}\n")
        
        
def search_runa():   
    if not appController._rune:
        appController._rune = Runa(appController._actionManager)
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.getRuna(key_name=key.get())
        key_entry.delete(0, tk.END)
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)

def load_runa():   
    if not appController._rune:
        appController._rune = Runa(appController._actionManager)
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.load_mappings()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)
        
def save_runa():   
    if not appController._rune:
        appController._rune = Runa(appController._actionManager)
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.save_mappings()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)
        
def list_runa():   
    if not appController._rune:
        appController._rune = Runa(appController._actionManager)
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.list_mappings()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)

def reset_runa():  
    if not appController._rune:
        appController._rune = Runa(appController._actionManager)  
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._rune.resetRuna(key_name=key.get())
        key_entry.delete(0, tk.END)
    out = buf.getvalue()
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)

def start_macro_rune():
    if not appController._rune:
        appController._rune = Runa(appController._actionManager)
    appController._rune.Atacar(True)
    macro_rune_start_btn.config(state=tk.DISABLED)
    macro_rune_stop_btn.config(state=tk.NORMAL)

def stop_macro_rune():  
    # sinaliza para o módulo de runas parar; assume que MacroRune.MagicRune(False) apenas define uma flag
    # from .macroRuneAutomatica import MacroRune
    try:
        Runa.Atacar(False)
    except Exception:
        # se ocorrer erro ao sinalizar, habilita os botões de qualquer forma
        macro_rune_start_btn.config(state=tk.NORMAL)
        macro_rune_stop_btn.config(state=tk.DISABLED)
        return
    # opcional: aguarda o worker encerrar em background e atualiza os botões quando terminar
    def waiter(th):
        th.join(timeout=10)
        root.after(0, lambda: (macro_rune_start_btn.config(state=tk.NORMAL), macro_rune_stop_btn.config(state=tk.DISABLED)))
    th = getattr(Runa, "_thread", None)
    if th:
        threading.Thread(target=waiter, args=(th,), daemon=True).start()
    else:
        macro_rune_start_btn.config(state=tk.NORMAL)
        macro_rune_stop_btn.config(state=tk.DISABLED)

def reset_coordinates():    
    if not appController._fishing:
        appController._fishing = Pesca(appController._actionManager)
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._fishing.resetCoordinates()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"

    returnBox.insert("1.0", out)

def search_varinha():   
    if not appController._fishing:
        appController._fishing = Pesca(appController._actionManager)
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._fishing.getFishingRod()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)

def search_aguas():   
    if not appController._fishing:
        appController._fishing = Pesca(appController._actionManager)
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        appController._fishing.getWaters()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)

def start_pesca():
    if not appController._fishing:
        appController._fishing = Pesca(appController._actionManager)
    # inicia a pesca (Pesca.Pescar cria a sua própria thread interna)
    if appController._fishing.varinha is None:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Necessário definir a varinha de pesca antes de iniciar.\n")
        return
    if not appController._fishing.watersCoords:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Necessário definir ao menos uma água antes de iniciar.\n")
        return
    if appController._fishing.status == Status.Inactive:
        appController._fishing.Pescar()
        start_btn.config(state=tk.DISABLED)
        stop_btn.config(state=tk.NORMAL)
    else:
        start_btn.config(state=tk.NORMAL)
        stop_btn.config(state=tk.DISABLED)


def stop_pesca():
    """Para a pesca usando o mesmo mecanismo que o ESC (set do _stop_event).
    Garante que o listener de teclado e a thread sejam sinalizados e aguardados.
    """
    if not appController._fishing:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Bot de pesca não está inicializado.\n")
        return

    f = appController._fishing
    try:
        try:
            f._stop_event.set()
        except Exception:
            pass

        try:
            if getattr(f, "_kb_listener", None):
                try:
                    f._kb_listener.stop()
                except Exception:
                    pass
                f._kb_listener = None
        except Exception:
            pass

        th = getattr(f, "_thread", None)
        if th and hasattr(th, "is_alive") and th.is_alive():
            th.join(timeout=3)

        try:
            f.status = Status.Inactive
        except Exception:
            pass
        # atualiza UI
        start_btn.config(state=tk.NORMAL)
        stop_btn.config(state=tk.DISABLED)

        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Pesca parada.\n")
    except Exception as e:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", f"Erro ao parar pesca: {e}\n")


root = tk.Tk()
root.title("Helper")
root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)	

mainframe = ttk.Frame(root, padding=(3, 3, 12, 12))
mainframe.grid(column=0, row=0, sticky=(N, S, W, E))

window_frame = ttk.LabelFrame(mainframe, text="Window Selection", padding=(5, 5, 5, 5))
window_frame.grid(column=1, row=1, columnspan=5, sticky=(W, E))
window_frame.columnconfigure(1, weight=1)  # make combobox expand
window_select_btn = ttk.Button(window_frame, text="Get Windows", command=get_windows)
window_select_btn.grid(column=0, row=0, padx=5)
combo = ttk.Combobox(
    window_frame,
    state="readonly",
    width=40  # adjust width as needed
)
combo.grid(column=1, row=0, padx=5, sticky=(W, E))
window_select_btn = ttk.Button(window_frame, text="Select Window", command=select_window)
window_select_btn.grid(column=5, row=0, padx=5)


label_key = tk.Label(mainframe, text="Hotkey:")
label_key.grid(column=1, row=2, sticky=(W, E))
key = StringVar()
key_entry = tk.Entry(mainframe, width=1, textvariable=key)
key_entry.grid(column=2, row=2, sticky=(W, E))
rune_select_btn = tk.Button(mainframe, text="Get Rune", command=search_runa)
rune_select_btn.grid(column=3, row=2, sticky=(W, E))
list_runas_btn = tk.Button(mainframe, text="List Preset", command=list_runa)
list_runas_btn.grid(column=4, row=2, sticky=(W, E))
sobrepor_btn = tk.Button(mainframe, text="Sobrepor Tela", command=sobrepor_todas_janelas)
sobrepor_btn.grid(column=5, row=2, sticky=(W, E))
sobrepor_btn.configure(background="lightcoral")

save_runas_btn = tk.Button(mainframe, text="Save Preset", command=save_runa)
save_runas_btn.grid(column=1, row=3, sticky=(W, E))
load_runas_btn = tk.Button(mainframe, text="Load Preset", command=load_runa)
load_runas_btn.grid(column=2, row=3, sticky=(W, E))
macro_rune_start_btn = tk.Button(mainframe, text="Start Macro", command=start_macro_rune)
macro_rune_start_btn.grid(column=3, row=3, sticky=(W, E))
macro_rune_stop_btn = tk.Button(mainframe, text="Stop Macro", command=stop_macro_rune, state=tk.DISABLED)
macro_rune_stop_btn.grid(column=4, row=3, sticky=(W, E))
reset_runas_btn = tk.Button(mainframe, text="Reset Runes", command=reset_runa)
reset_runas_btn.grid(column=5, row=3, sticky=(W, E))

busca_varinha_btn = tk.Button(mainframe, text="Get FishingRod", command=search_varinha)
busca_varinha_btn.grid(column=1, row=4, sticky=(W, E))
busca_water_btn = tk.Button(mainframe, text="Get Water", command=search_aguas)
busca_water_btn.grid(column=2, row=4, sticky=(W, E))
start_btn = tk.Button(mainframe, text="Start Fishing", command=start_pesca)
start_btn.grid(column=3, row=4, sticky=(W, E))
stop_btn = tk.Button(mainframe, text="Stop Fishing", command=stop_pesca, state=tk.DISABLED)
stop_btn.grid(column=4, row=4, sticky=(W, E))
reset_coordinates_btn = tk.Button(mainframe, text="Reset Fishing", command=reset_coordinates)
reset_coordinates_btn.grid(column=5, row=4, sticky=(W, E))

returnBox = tk.Text(mainframe, width=40, height=10)
returnBox.grid(column=1, row=5, columnspan=5, sticky=(W, E))

start_btn.configure(state=tk.DISABLED)
busca_varinha_btn.configure(state=tk.DISABLED)
busca_water_btn.configure(state=tk.DISABLED)


for child in mainframe.winfo_children(): 
    child.grid_configure(padx=5, pady=5)

appController = AppController()
root.mainloop()

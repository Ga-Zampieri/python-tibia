import contextlib
import io
import tkinter as tk
from tkinter import N, S, W, E, StringVar, ttk
from .pescaAutomatica import Pesca
from .macroRuna import Runa
from .auto_clicker import AutoClicker
import threading

root = tk.Tk()
root.title("Helper")
sobrepor_janela = False

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


mainframe = ttk.Frame(root, padding=(3, 3, 12, 12))
mainframe.grid(column=0, row=0, sticky=(N, S, W, E))
worker_thread = None
_worker_lock = threading.Lock()


def search_runa():   
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ret = Runa.getRuna(key_name=key.get())
        key_entry.delete(0, tk.END)
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)

def load_runa():   
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ret = Runa.load_mappings()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)
        
def save_runa():   
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ret = Runa.save_mappings()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)
        
def list_runa():   
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ret = Runa.list_mappings()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)

def reset_runa():    
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        Runa.resetRuna(key_name=key.get())
        key_entry.delete(0, tk.END)
    out = buf.getvalue()
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)

def start_macro_rune():
    Runa.Atacar(True)
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
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        Pesca.resetCoordinates()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"

    returnBox.insert("1.0", out)

def search_varinha():   
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        Pesca.getFishingRod()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)

def search_aguas():   
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        Pesca.getWaters()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)

def start_pesca():
    # inicia a pesca (Pesca.Pescar cria a sua própria thread interna)
    if Pesca.varinhaX is None or Pesca.varinhaY is None:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Necessário definir a varinha de pesca antes de iniciar.\n")
        return
    if not Pesca.watersCoords:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Necessário definir ao menos uma água antes de iniciar.\n")
        return
    Pesca.Pescar(True)
    start_btn.config(state=tk.DISABLED)
    stop_btn.config(state=tk.NORMAL)

    # Monitora a thread interna do Pesca e reabilita botões quando terminar
    def monitor(th):
        if th:
            th.join()  # espera o término da thread do bot
        root.after(0, lambda: (start_btn.config(state=tk.NORMAL), stop_btn.config(state=tk.DISABLED)))

    th = getattr(Pesca, "_thread", None)
    if th:
        threading.Thread(target=monitor, args=(th,), daemon=True).start()
    else:
        # fallback se não houver thread criada
        start_btn.config(state=tk.NORMAL)
        stop_btn.config(state=tk.DISABLED)

def stop_pesca():
    # sinaliza para o módulo de pesca parar; assume que Pesca.Pescar(False) apenas define uma flag
    try:
        Pesca.Pescar(False)
    except Exception:
        # se ocorrer erro ao sinalizar, habilita os botões de qualquer forma
        start_btn.config(state=tk.NORMAL)
        stop_btn.config(state=tk.DISABLED)
        return
    # opcional: aguarda o worker encerrar em background e atualiza os botões quando terminar
    def waiter(th):
        th.join(timeout=10)
        root.after(0, lambda: (start_btn.config(state=tk.NORMAL), stop_btn.config(state=tk.DISABLED)))
    with _worker_lock:
        th = worker_thread
    if th:
        threading.Thread(target=waiter, args=(th,), daemon=True).start()
    else:
        start_btn.config(state=tk.NORMAL)
        stop_btn.config(state=tk.DISABLED)

returnBox = tk.Text(mainframe, width=40, height=10)
returnBox.grid(column=1, row=4, columnspan=5, sticky=(W, E))

label_key = tk.Label(mainframe, text="Hotkey:")
label_key.grid(column=1, row=1, sticky=(W, E))
key = StringVar()
key_entry = tk.Entry(mainframe, width=1, textvariable=key)
key_entry.grid(column=2, row=1, sticky=(W, E))
rune_select_btn = tk.Button(mainframe, text="Get Rune", command=search_runa)
rune_select_btn.grid(column=3, row=1, sticky=(W, E))
list_runas_btn = tk.Button(mainframe, text="List Preset", command=list_runa)
list_runas_btn.grid(column=4, row=1, sticky=(W, E))
sobrepor_btn = tk.Button(mainframe, text="Sobrepor Tela", command=sobrepor_todas_janelas)
sobrepor_btn.grid(column=5, row=1, sticky=(W, E))
sobrepor_btn.configure(background="lightcoral")

save_runas_btn = tk.Button(mainframe, text="Save Preset", command=save_runa)
save_runas_btn.grid(column=1, row=2, sticky=(W, E))
load_runas_btn = tk.Button(mainframe, text="Load Preset", command=load_runa)
load_runas_btn.grid(column=2, row=2, sticky=(W, E))
macro_rune_start_btn = tk.Button(mainframe, text="Start Macro", command=start_macro_rune)
macro_rune_start_btn.grid(column=3, row=2, sticky=(W, E))
macro_rune_stop_btn = tk.Button(mainframe, text="Stop Macro", command=stop_macro_rune, state=tk.DISABLED)
macro_rune_stop_btn.grid(column=4, row=2, sticky=(W, E))
reset_runas_btn = tk.Button(mainframe, text="Reset Runes", command=reset_runa)
reset_runas_btn.grid(column=5, row=2, sticky=(W, E))

busca_varinha_btn = tk.Button(mainframe, text="Get FishingRod", command=search_varinha)
busca_varinha_btn.grid(column=1, row=3, sticky=(W, E))
busca_water_btn = tk.Button(mainframe, text="Get Water", command=search_aguas)
busca_water_btn.grid(column=2, row=3, sticky=(W, E))
start_btn = tk.Button(mainframe, text="Start Fishing", command=start_pesca)
start_btn.grid(column=3, row=3, sticky=(W, E))
stop_btn = tk.Button(mainframe, text="Stop Fishing", command=stop_pesca, state=tk.DISABLED)
stop_btn.grid(column=4, row=3, sticky=(W, E))
reset_coordinates_btn = tk.Button(mainframe, text="Reset Fishing", command=reset_coordinates)
reset_coordinates_btn.grid(column=5, row=3, sticky=(W, E))


# Adicionando botões para capturar coordenadas e iniciar/parar o auto_clicker

def capture_coordinates():
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        count = int(coord_count.get()) if coord_count.get().isdigit() else 2
        AutoClicker.getCoords(count=count)
    out = buf.getvalue()

    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)

def start_auto_clicker():
    if not AutoClicker.Coords:
        returnBox.delete("1.0", tk.END)
        returnBox.insert("1.0", "Necessário definir coordenadas antes de iniciar.\n")
        return
    AutoClicker.Clickar(True)
    auto_clicker_start_btn.config(state=tk.DISABLED)
    auto_clicker_stop_btn.config(state=tk.NORMAL)

    # Monitora a thread interna do Pesca e reabilita botões quando terminar
    def monitor(th):
        if th:
            th.join()  # espera o término da thread do bot
        root.after(0, lambda: (auto_clicker_start_btn.config(state=tk.NORMAL), auto_clicker_stop_btn.config(state=tk.DISABLED)))

    th = getattr(AutoClicker, "_thread", None)
    if th:
        threading.Thread(target=monitor, args=(th,), daemon=True).start()
    else:
        # fallback se não houver thread criada
        auto_clicker_start_btn.config(state=tk.NORMAL)
        auto_clicker_stop_btn.config(state=tk.DISABLED)
    

def stop_auto_clicker():
    try:
        AutoClicker.Clickar(False)
    except Exception:
        # se ocorrer erro ao sinalizar, habilita os botões de qualquer forma
        auto_clicker_start_btn.config(state=tk.NORMAL),
        auto_clicker_stop_btn.config(state=tk.DISABLED)
        return
    auto_clicker_start_btn.config(state=tk.NORMAL),
    auto_clicker_stop_btn.config(state=tk.DISABLED)
    # opcional: aguarda o worker encerrar em background e atualiza os botões quando terminar
    def waiter(th):
        th.join(timeout=10)
        root.after(0, lambda: (auto_clicker_start_btn.config(state=tk.NORMAL), auto_clicker_stop_btn.config(state=tk.DISABLED)))
    with _worker_lock:
        th = worker_thread
    if th:
        threading.Thread(target=waiter, args=(th,), daemon=True).start()
    else:
        auto_clicker_start_btn.config(state=tk.NORMAL)
        auto_clicker_stop_btn.config(state=tk.DISABLED)


# Adicionando novos elementos à interface
label_coord_count = tk.Label(mainframe, text="Qtd Coordenadas:")
label_coord_count.grid(column=1, row=5, sticky=(W, E))
coord_count = StringVar()
coord_count_entry = tk.Entry(mainframe, width=5, textvariable=coord_count)
coord_count_entry.grid(column=2, row=5, sticky=(W, E))

capture_coords_btn = tk.Button(mainframe, text="Capture Coords", command=capture_coordinates)
capture_coords_btn.grid(column=3, row=5, sticky=(W, E))

auto_clicker_start_btn = tk.Button(mainframe, text="Start AutoClicker", command=start_auto_clicker)
auto_clicker_start_btn.grid(column=4, row=5, sticky=(W, E))

auto_clicker_stop_btn = tk.Button(mainframe, text="Stop AutoClicker", command=stop_auto_clicker, state=tk.DISABLED)
auto_clicker_stop_btn.grid(column=5, row=5, sticky=(W, E))


root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)	

for child in mainframe.winfo_children(): 
    child.grid_configure(padx=5, pady=5)

# Start the event loop
root.mainloop()

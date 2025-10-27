import contextlib
import io
import tkinter as tk
from tkinter import N, S, W, E, ttk
from .pescaAutomatica import Pesca
from .macroRuna import Runa
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
        ret = Runa.getRuna()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)
    if ret:
        rune_select_btn.configure(background="lightgreen")
    else:
        rune_select_btn.configure(background="lightcoral")

def reset_runa():    
    returnBox.delete("1.0", tk.END)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        Runa.resetRuna()
    out = buf.getvalue()
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)
    rune_select_btn.configure(background="SystemButtonFace")
    rune_select_btn.configure(background="SystemButtonFace")

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
    busca_water_btn.configure(background="SystemButtonFace")
    busca_varinha_btn.configure(background="SystemButtonFace")


def search_varinha():   
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ret = Pesca.getFishingRod()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)
    if ret:
        busca_varinha_btn.configure(background="lightgreen")
    else:
        busca_varinha_btn.configure(background="lightcoral")

def search_aguas():   
    returnBox.delete("1.0", tk.END)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ret = Pesca.getWaters()
    out = buf.getvalue()
    
    if not out:
        out = "Nenhum resultado registrado.\n"
    returnBox.insert("1.0", out)
    if ret:
        busca_water_btn.configure(background="lightgreen")
    else:
        busca_water_btn.configure(background="lightcoral")

def start_pesca():
    # inicia a pesca (Pesca.Pescar cria a sua própria thread interna)
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

sobrepor_btn = tk.Button(mainframe, text="Sobrepor Tela", command=sobrepor_todas_janelas)
sobrepor_btn.grid(column=1, row=1, sticky=(W, E))
sobrepor_btn.configure(background="lightcoral")
rune_select_btn = tk.Button(mainframe, text="Buscar Runa", command=search_runa)
rune_select_btn.grid(column=2, row=1, sticky=(W, E))
macro_rune_start_btn = tk.Button(mainframe, text="Macro Rune Start", command=start_macro_rune)
macro_rune_start_btn.grid(column=3, row=1, sticky=(W, E))
macro_rune_stop_btn = tk.Button(mainframe, text="Macro Rune Stop", command=stop_macro_rune, state=tk.DISABLED)
macro_rune_stop_btn.grid(column=4, row=1, sticky=(W, E))
reset_runas_btn = tk.Button(mainframe, text="Reset Runas", command=reset_runa)
reset_runas_btn.grid(column=5, row=1, sticky=(W, E))

busca_varinha_btn = tk.Button(mainframe, text="Buscar Varinha", command=search_varinha)
busca_varinha_btn.grid(column=1, row=2, sticky=(W, E))
busca_water_btn = tk.Button(mainframe, text="Buscar Águas", command=search_aguas)
busca_water_btn.grid(column=2, row=2, sticky=(W, E))
start_btn = tk.Button(mainframe, text="Iniciar Pesca", command=start_pesca)
start_btn.grid(column=3, row=2, sticky=(W, E))
stop_btn = tk.Button(mainframe, text="Parar Pesca", command=stop_pesca, state=tk.DISABLED)
stop_btn.grid(column=4, row=2, sticky=(W, E))
reset_coordinates_btn = tk.Button(mainframe, text="Reset Pesca", command=reset_coordinates)
reset_coordinates_btn.grid(column=5, row=2, sticky=(W, E))

root.columnconfigure(0, weight=1)
root.rowconfigure(0, weight=1)	

for child in mainframe.winfo_children(): 
    child.grid_configure(padx=5, pady=5)

# Start the event loop
root.mainloop()

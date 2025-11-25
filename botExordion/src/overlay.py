import tkinter as tk
import win32gui
import win32con
import win32api
import time
import threading
from tkinter import ttk
import io
import contextlib

# Configurações
OVERLAY_WIDTH = 300
OVERLAY_HEIGHT = 255
ALPHA = 200

class OverlayApp:
    def __init__(self, parent_hwnd, app_controller):
        self.parent_hwnd = parent_hwnd
        self.app_controller = app_controller
        self.root = None
        self.running = True
        self.is_minimized = False
        self.minimized_height = 35
        
    def create_overlay(self):
        """Cria a interface do overlay na thread principal"""
        try:
            # Cria uma janela Tk independente
            self.root = tk.Toplevel()
            self.root.title("Helper Overlay")
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", False)
            self.root.configure(bg='#2a2a2a')
            self.root.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}")
            
            # Remove o ícone da barra de tarefas
            self.root.attributes("-toolwindow", True)
            self.root.attributes("-alpha", 0.8)  # Mais opaco para melhor visibilidade
            
            # Frame principal
            main_frame = ttk.Frame(self.root, padding="5")
            main_frame.pack(fill="both", expand=True)
            
            # Barra de título personalizada
            title_bar = ttk.Frame(main_frame, height=20)
            title_bar.pack(fill="x", pady=(0, 5))
            title_bar.pack_propagate(False)
            
            # Título e botão de minimizar
            title_label = ttk.Label(title_bar, text="Helper Overlay", 
                                   font=("Arial", 9, "bold"),
                                   foreground="white",
                                   background="#3a3a3a")
            title_label.pack(side="left", padx=5)
            
            # Botão de minimizar
            self.minimize_btn = ttk.Button(title_bar, text="−", width=2,
                                          command=self.toggle_minimize)
            self.minimize_btn.pack(side="right", padx=2)
            
            # Container do conteúdo
            self.content_container = ttk.Frame(main_frame)
            self.content_container.pack(fill="both", expand=True)
            
            # Container principal com layout horizontal
            horizontal_container = ttk.Frame(self.content_container)
            horizontal_container.pack(fill="both", expand=True)
            
            # Coluna da ESQUERDA - Runa Macros
            left_column = ttk.Frame(horizontal_container)
            left_column.pack(side="left", fill="both", expand=True, padx=(0, 3))
            
            # Frame para Runa Macros
            rune_frame = ttk.LabelFrame(left_column, text="Runa Macros", padding="4")
            rune_frame.pack(fill="both", expand=True)
            
            # Hotkey + Get Rune
            hotkey_frame = ttk.Frame(rune_frame)
            hotkey_frame.pack(fill="x", pady=(0, 4))
            
            ttk.Label(hotkey_frame, text="Hotkey:", font=("Arial", 8)).pack(side="left")
            self.key_var = tk.StringVar()
            key_entry = ttk.Entry(hotkey_frame, textvariable=self.key_var, width=4, font=("Arial", 8))
            key_entry.pack(side="left", padx=3)
            
            ttk.Button(hotkey_frame, text="Get Rune", 
                      command=self.get_runa, width=8).pack(side="left")
            
            # Botões de runa em grid 2x2
            rune_buttons_frame = ttk.Frame(rune_frame)
            rune_buttons_frame.pack(fill="both", expand=True, pady=2)
            
            # Botões com fonte legível
            btn_style = ttk.Style()
            btn_style.configure("Compact.TButton", font=("Arial", 8))
            
            # Linha 1
            ttk.Button(rune_buttons_frame, text="List Preset", style="Compact.TButton",
                      command=self.list_runa).grid(row=0, column=0, sticky="ew", padx=1, pady=1)
            ttk.Button(rune_buttons_frame, text="Save Preset", style="Compact.TButton",
                      command=self.save_runa).grid(row=0, column=1, sticky="ew", padx=1, pady=1)
            
            # Linha 2
            ttk.Button(rune_buttons_frame, text="Load Preset", style="Compact.TButton",
                      command=self.load_runa).grid(row=1, column=0, sticky="ew", padx=1, pady=1)
            ttk.Button(rune_buttons_frame, text="Reset Runes", style="Compact.TButton",
                      command=self.reset_runa).grid(row=1, column=1, sticky="ew", padx=1, pady=1)
            
            # Configurar pesos iguais para as colunas
            rune_buttons_frame.columnconfigure(0, weight=1)
            rune_buttons_frame.columnconfigure(1, weight=1)
            
            # Frame para macro runa
            macro_frame = ttk.LabelFrame(rune_frame, text="Macro Control", padding="2")
            macro_frame.pack(fill="x", pady=(3, 0))
            
            self.macro_start_btn = ttk.Button(macro_frame, text="Start Macro", style="Compact.TButton",
                                             command=self.start_macro_runa)
            self.macro_start_btn.pack(fill="x", pady=1)
            
            self.macro_stop_btn = ttk.Button(macro_frame, text="Stop Macro", style="Compact.TButton",
                                            command=self.stop_macro_runa, state="disabled")
            self.macro_stop_btn.pack(fill="x", pady=1)
            
            # Coluna da DIREITA - Fishing
            right_column = ttk.Frame(horizontal_container)
            right_column.pack(side="right", fill="both", expand=True, padx=(3, 0))
            
            # Frame para Fishing
            fishing_frame = ttk.LabelFrame(right_column, text="Fishing", padding="4")
            fishing_frame.pack(fill="both", expand=True)
            
            # Botões de fishing
            ttk.Button(fishing_frame, text="Get Fishing Rod", style="Compact.TButton",
                      command=self.get_fishing_rod).pack(fill="x", pady=1)
            ttk.Button(fishing_frame, text="Get Water", style="Compact.TButton",
                      command=self.get_water).pack(fill="x", pady=1)
            ttk.Button(fishing_frame, text="Reset Fishing", style="Compact.TButton",
                      command=self.reset_fishing).pack(fill="x", pady=1)
            
            # Botões start/stop fishing
            fishing_control_frame = ttk.Frame(fishing_frame)
            fishing_control_frame.pack(fill="x", pady=(4, 0))
            
            self.fishing_start_btn = ttk.Button(fishing_control_frame, text="Start Fishing", style="Compact.TButton",
                                               command=self.start_fishing)
            self.fishing_start_btn.pack(fill="x", pady=1)
            
            self.fishing_stop_btn = ttk.Button(fishing_control_frame, text="Stop Fishing", style="Compact.TButton",
                                              command=self.stop_fishing, state="disabled")
            self.fishing_stop_btn.pack(fill="x", pady=1)
            
            # Botão para fechar
            close_frame = ttk.Frame(self.content_container)
            close_frame.pack(fill="x", pady=(5, 0))
            
            ttk.Button(close_frame, text="Close Overlay", style="Compact.TButton",
                      command=self.close_overlay).pack(fill="x")
            
            # Configurações da janela
            self.setup_window()
            
            # Inicia a sincronização
            self.start_sync()
            
            print("Overlay criado com sucesso! (Sempre clicável)")
            
        except Exception as e:
            print(f"Erro ao criar overlay: {e}")
    
    def toggle_minimize(self):
        """Alterna entre minimizado e normal"""
        try:
            if self.is_minimized:
                # Restaura
                self.root.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}")
                self.content_container.pack(fill="both", expand=True)
                self.minimize_btn.config(text="−")
                self.is_minimized = False
                print("Overlay restaurado")
            else:
                # Minimiza
                self.root.geometry(f"{OVERLAY_WIDTH}x{self.minimized_height}")
                self.content_container.pack_forget()
                self.minimize_btn.config(text="+")
                self.is_minimized = True
                print("Overlay minimizado")
        except Exception as e:
            print(f"Erro em toggle_minimize: {e}")
        
    def close_overlay(self):
        """Fecha o overlay"""
        try:
            self.running = False
            if self.root:
                self.root.quit()
                self.root.destroy()
            print("Overlay fechado")
        except Exception as e:
            print(f"Erro ao fechar overlay: {e}")
    
    def setup_window(self):
        """Configura as propriedades da janela overlay"""
        try:
            hwnd_overlay = self.root.winfo_id()
            style = win32gui.GetWindowLong(hwnd_overlay, win32con.GWL_EXSTYLE)
            style |= win32con.WS_EX_LAYERED
            
            win32gui.SetWindowLong(hwnd_overlay, win32con.GWL_EXSTYLE, style)
            
            win32gui.SetLayeredWindowAttributes(hwnd_overlay, 0, ALPHA, win32con.LWA_ALPHA)
        
            win32gui.SetWindowLong(hwnd_overlay, win32con.GWL_HWNDPARENT, self.parent_hwnd)
            
        except Exception as e:
            print(f"Erro no setup_window: {e}")
    
    def start_sync(self):
        """Inicia a sincronização usando after()"""
        self.sync_position()
    
    def sync_position(self):
        """Sincroniza a posição do overlay com a janela pai"""
        if not self.running or not self.root or not self.parent_hwnd:
            return
            
        try:
            # Verifica se a janela pai ainda existe
            if not win32gui.IsWindow(self.parent_hwnd):
                print("Janela pai não existe mais")
                self.close_overlay()
                return
            
            # Obtém estado e posição da janela pai
            parent_rect = win32gui.GetWindowRect(self.parent_hwnd)
            parent_left, parent_top, parent_right, parent_bottom = parent_rect
            
            if win32gui.IsIconic(self.parent_hwnd):
                self.root.withdraw()
            else:
                self.root.deiconify()
                current_height = self.minimized_height if self.is_minimized else OVERLAY_HEIGHT
                overlay_x = parent_left + 10
                overlay_y = parent_bottom - current_height - 10
                
                self.root.geometry(f"{OVERLAY_WIDTH}x{current_height}+{overlay_x}+{overlay_y}")
                
                parent_style = win32gui.GetWindowLong(self.parent_hwnd, win32con.GWL_EXSTYLE)
                is_parent_topmost = (parent_style & win32con.WS_EX_TOPMOST) != 0
                
                if is_parent_topmost:
                    self.root.attributes("-topmost", True)
                else:
                    self.root.attributes("-topmost", False)
            
            self.root.attributes("-alpha", 0.8)  # Opacidade fixa
            
        except Exception as e:
            print(f"Erro no sync_position: {e}")
        
        # Agenda a próxima sincronização
        if self.running:
            self.root.after(500, self.sync_position)
    
    # Métodos para Runa
    def get_runa(self):
        try:
            if self.app_controller._rune:
                key_name = self.key_var.get()
                if not key_name:
                    self.log_to_main_app("Erro: Informe uma hotkey primeiro")
                    return
                    
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.app_controller._rune.getRuna(key_name=key_name)
                out = buf.getvalue()
                self.log_to_main_app(out)
        except Exception as e:
            self.log_to_main_app(f"Erro em get_runa: {e}")
    
    def list_runa(self):
        try:
            if self.app_controller._rune:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.app_controller._rune.list_mappings()
                out = buf.getvalue()
                self.log_to_main_app(out)
        except Exception as e:
            self.log_to_main_app(f"Erro em list_runa: {e}")
    
    def save_runa(self):
        try:
            if self.app_controller._rune:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.app_controller._rune.save_mappings()
                out = buf.getvalue()
                self.log_to_main_app(out)
        except Exception as e:
            self.log_to_main_app(f"Erro em save_runa: {e}")
    
    def load_runa(self):
        try:
            if self.app_controller._rune:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.app_controller._rune.load_mappings()
                out = buf.getvalue()
                self.log_to_main_app(out)
        except Exception as e:
            self.log_to_main_app(f"Erro em load_runa: {e}")
    
    def reset_runa(self):
        try:
            if self.app_controller._rune:
                key_name = self.key_var.get()
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.app_controller._rune.resetRuna(key_name=key_name if key_name else None)
                out = buf.getvalue()
                self.log_to_main_app(out)
        except Exception as e:
            self.log_to_main_app(f"Erro em reset_runa: {e}")
    
    def start_macro_runa(self):
        try:
            if self.app_controller._rune:
                self.app_controller._rune.Atacar()
        except Exception as e:
            self.log_to_main_app(f"Erro em start_macro_runa: {e}")
    
    def stop_macro_runa(self):
        try:
            if self.app_controller._rune:
                self.app_controller._rune.Atacar()
        except Exception as e:
            self.log_to_main_app(f"Erro em stop_macro_runa: {e}")
    
    # Métodos para Pesca
    def get_fishing_rod(self):
        try:
            if self.app_controller._fishing:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.app_controller._fishing.getFishingRod()
                out = buf.getvalue()
                self.log_to_main_app(out)
        except Exception as e:
            self.log_to_main_app(f"Erro em get_fishing_rod: {e}")
    
    def get_water(self):
        try:
            if self.app_controller._fishing:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.app_controller._fishing.getWaters()
                out = buf.getvalue()
                self.log_to_main_app(out)
        except Exception as e:
            self.log_to_main_app(f"Erro em get_water: {e}")
    
    def reset_fishing(self):
        try:
            if self.app_controller._fishing:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    self.app_controller._fishing.resetCoordinates()
                out = buf.getvalue()
                self.log_to_main_app(out)
        except Exception as e:
            self.log_to_main_app(f"Erro em reset_fishing: {e}")
    
    def start_fishing(self):
        try:
            if self.app_controller._fishing:
                if self.app_controller._fishing.varinha is None:
                    self.log_to_main_app("Erro: Defina a varinha primeiro.")
                    return
                if not self.app_controller._fishing.watersCoords:
                    self.log_to_main_app("Erro: Defina as águas primeiro.")
                    return
                    
                if self.app_controller._fishing.status == 0:
                    self.app_controller._fishing.Pescar()
        except Exception as e:
            self.log_to_main_app(f"Erro em start_fishing: {e}")
    
    def stop_fishing(self):
        try:
            if self.app_controller._fishing:
                self.app_controller._fishing._stop()
        except Exception as e:
            self.log_to_main_app(f"Erro em stop_fishing: {e}")
    
    def log_to_main_app(self, message):
        """Envia mensagens para a aplicação principal"""
        try:
            if hasattr(self.app_controller, '_main_app_returnBox'):
                returnBox = self.app_controller._main_app_returnBox
                returnBox.delete("1.0", tk.END)
                returnBox.insert("1.0", message)
                returnBox.see("1.0")
        except Exception as e:
            print(f"Erro ao logar na app principal: {e}")

# Variável global para instância do overlay
overlay_instance = None

def create_overlay(parent_hwnd, app_controller):
    """Cria o overlay para a janela especificada"""
    global overlay_instance
    
    try:
        # Fecha overlay existente
        if overlay_instance:
            try:
                overlay_instance.close_overlay()
            except Exception as e:
                print(f"Erro ao fechar overlay existente: {e}")
            time.sleep(0.1)
        
        # Cria novo overlay
        overlay_instance = OverlayApp(parent_hwnd, app_controller)
        overlay_instance.create_overlay()
        
        return overlay_instance
        
    except Exception as e:
        print(f"Erro em create_overlay: {e}")
        return None

def update_overlay_buttons():
    """Atualiza o estado dos botões no overlay"""
    global overlay_instance
    if overlay_instance and overlay_instance.root:
        try:
            if overlay_instance.app_controller._rune:
                status = overlay_instance.app_controller._rune.status
                if status == 1:
                    overlay_instance.macro_start_btn.config(state="disabled")
                    overlay_instance.macro_stop_btn.config(state="normal")
                else:
                    overlay_instance.macro_start_btn.config(state="normal")
                    overlay_instance.macro_stop_btn.config(state="disabled")
            
            if overlay_instance.app_controller._fishing:
                status = overlay_instance.app_controller._fishing.status
                if status == 1:
                    overlay_instance.fishing_start_btn.config(state="disabled")
                    overlay_instance.fishing_stop_btn.config(state="normal")
                else:
                    overlay_instance.fishing_start_btn.config(state="normal")
                    overlay_instance.fishing_stop_btn.config(state="disabled")
        except Exception as e:
            print(f"Erro em update_overlay_buttons: {e}")
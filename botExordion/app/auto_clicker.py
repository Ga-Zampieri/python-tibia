import random
import pyautogui as pgui
from pynput import mouse, keyboard
import threading
import time

class AutoClicker:
    _thread = None
    _stop_event = threading.Event()
    _kb_listener = None
    Coords = []

    @classmethod
    def _on_key_press(cls, key):
        try:
            if key == keyboard.Key.esc:
                print("ESC pressionado — solicitando parada do bot")
                cls._stop_event.set()
        except Exception:
            pass

    @classmethod
    def Clickar(cls, status: bool):
        if status:
            if cls._thread and cls._thread.is_alive():
                return  # já rodando
            if cls._kb_listener is None or not getattr(cls._kb_listener, "is_alive", lambda: False)():
                cls._kb_listener = keyboard.Listener(on_press=cls._on_key_press)
                cls._kb_listener.daemon = True
                cls._kb_listener.start()

            cls._stop_event.clear()
            cls._thread = threading.Thread(target=cls._run, daemon=True)
            cls._thread.start()
        else:
            cls._stop_event.set()
            # encerra listener de teclado se existir
            try:
                if cls._kb_listener is not None:
                    cls._kb_listener.stop()
            except Exception:
                pass
            cls._kb_listener = None

    
    @classmethod
    def getCoords(cls, count: int = 2, timeout: int = 20):
        """Captura `count` cliques sequenciais (padrão 5) e adiciona a cls.Coords.
        Se o timeout expirar antes de obter todos, adiciona o que foi capturado.
        Chamadas subsequentes apenas acrescentam à lista existente.
        """
        collected = []

        def _on_click(x, y, button, pressed):
            if pressed:
                collected.append((int(x), int(y)))
                print(f"Capturado {len(collected)}/{count}: {collected[-1]}")
                if len(collected) >= count:
                    return False  # para o listener quando atingir o número desejado

        try:
            print(f"Buscando {count} coordenadas (clique {count} vezes)...")
            listener = mouse.Listener(on_click=_on_click)
            listener.start()

            end_time = time.time() + timeout
            # aguarda até coletar count cliques ou até timeout
            while time.time() < end_time and len(collected) < count:
                time.sleep(0.1)

            # garantir parada do listener
            try:
                listener.stop()
            except Exception:
                pass

            if collected:
                cls.Coords = collected
                print(f"Coordenadas totais: {cls.Coords}")
            else:
                print("Nenhuma coordenada registrada (timeout).")
            return True
        except Exception as e:
            print(f"Erro ao localizar coordenadas: {e}")
        finally:
            pass

    @classmethod
    def resetCoordinates(cls):
        cls.Coords = []
        print("Coordenadas resetadas.")

    @classmethod
    def _run(cls):
        try:   
            while not cls._stop_event.is_set():
                for _ in cls.Coords:
                    if cls._stop_event.is_set():
                        return
                    randX = random.randint(-4, 4)
                    randY = random.randint(-1, 1)
                    
                    pgui.moveTo(_[0]+randX, _[1]+randY)
                    pgui.click()
                    for i in range(5):
                        if cls._stop_event.is_set():
                            return
                        time.sleep(0.1)
        finally:
            cls._stop_event.set()
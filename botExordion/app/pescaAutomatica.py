import random
import pyautogui as pgui
from pynput import mouse, keyboard
import threading
import time

class Pesca:
    _thread = None
    _stop_event = threading.Event()
    _kb_listener = None
    varinhaX = None
    varinhaY = None
    watersCoords = []

    @classmethod
    def _on_key_press(cls, key):
        try:
            if key == keyboard.Key.esc:
                print("ESC pressionado — solicitando parada do bot")
                cls._stop_event.set()
        except Exception:
            pass

    @classmethod
    def Pescar(cls, status: bool):
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
    def getFishingRod(cls):
        def _on_click(x, y, pressed):
            if pressed:
                coords['x'], coords['y'] = int(x), int(y)
                return False  # stop listener
        try:
            print("Buscando Varinha de Pesca")
            coords = {}
            timeout = 10  # segundos
            
            listener = mouse.Listener(on_click=_on_click)
            listener.start()
            listener.join(timeout)  # aguarda até o clique ou timeout
            listener.stop()    
            if 'x' in coords:
                cls.varinhaX, cls.varinhaY = coords['x'], coords['y']
            print(f"Varinha encontrada em: X{cls.varinhaX}, Y {cls.varinhaY}")
            return True
        except Exception as e:
            print(f"Erro ao localizar varinha: {e}")
        finally:
            pass
    
    @classmethod
    def getWaters(cls):
        def _on_click(x, y, pressed):
            if pressed:
                coords['x'], coords['y'] = int(x), int(y)
                return False  # stop listener
        try:
            print("Buscando Águas")
            coords = {}
            timeout = 10  # segundos
            
            listener = mouse.Listener(on_click=_on_click)
            listener.start()
            listener.join(timeout)  # aguarda até o clique ou timeout
            listener.stop()    
            if 'x' in coords:
                coords = coords['x'], coords['y']
                cls.watersCoords.append(coords)
            print(f"Águas encontradas em: {cls.watersCoords}")
            return True
        except Exception as e:
            print(f"Erro ao localizar águas: {e}")
        finally:
            pass

    @classmethod
    def resetCoordinates(cls):
        cls.varinhaX = None
        cls.varinhaY = None
        cls.watersCoords = []
        print("Coordenadas de varinha e águas resetadas.")

    @classmethod
    def _run(cls):
        try:   
            while not cls._stop_event.is_set():
                for _ in cls.watersCoords:
                    for i in range(10):
                        if cls._stop_event.is_set():
                            return
                        randX = random.randint(-10, 10)
                        randY = random.randint(-10, 10)
                        
                        pgui.moveTo(cls.varinhaX + randX, cls.varinhaY + randY)
                        pgui.rightClick()
                        for i in range(5):
                            if cls._stop_event.is_set():
                                return
                            time.sleep(0.1)
                        pgui.moveTo(_[0]+randX, _[1]+randY)
                        pgui.click()
                        for i in range(5):
                            if cls._stop_event.is_set():
                                return
                            time.sleep(0.1)
        finally:
            cls._stop_event.set()
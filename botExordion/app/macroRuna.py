import random
import pyautogui as pgui
from pynput import mouse, keyboard
import threading
import time

class Runa:
    _thread = None
    _stop_event = threading.Event()
    _kb_listener = None
    runaX = None
    runaY = None

    @classmethod
    def _on_key_press(cls, key):
        try:
            if key == keyboard.Key.esc:
                # print("ESC pressionado — solicitando parada do bot")
                cls._stop_event.set()
            if key == keyboard.Key.f1:
                # Ao pressionar F1, tentar equipar a runa (mover até as coordenadas e clicar com botão direito)
                # print("F1 pressionado — equipando runa")
                try:
                    cls.equipRuna()
                except Exception as e:
                    print(f"Erro ao tentar equipar runa: {e}")
                
        except Exception:
            pass

    @classmethod
    def equipRuna(cls):
        """Move o mouse até as coordenadas da runa e executa um clique direito.

        Se as coordenadas não estiverem configuradas, chama `getRuna` para capturar
        as coordenadas pelo clique do usuário.
        """
        # Se não temos coordenadas, pedir que o usuário clique na runa para registrar
        if cls.runaX is None or cls.runaY is None:
            print("Coordenadas da runa não definidas. Aguarde e clique na runa para registrar...")
            ok = cls.getRuna()
            if not ok or cls.runaX is None or cls.runaY is None:
                print("Falha ao obter coordenadas da runa. Operação cancelada.")
                return

        # Movimenta o mouse e clica com o botão direito
        try:
            # Pequena duração para parecer mais natural e permitir cancelamento
            pgui.moveTo(cls.runaX, cls.runaY, duration=0.05)
            pgui.click(button='right')
        except Exception as e:
            print(f"Erro durante o clique na runa: {e}")

    @classmethod
    def Atacar(cls, status: bool):
        if status:
            if cls._thread and cls._thread.is_alive():
                return  # já rodando
            # Apenas inicia o listener de teclado. Não dispare uma thread que clique
            # imediatamente — queremos que o clique ocorra somente ao pressionar F1.
            if cls._kb_listener is None or not getattr(cls._kb_listener, "is_alive", lambda: False)():
                cls._kb_listener = keyboard.Listener(on_press=cls._on_key_press)
                cls._kb_listener.daemon = True
                cls._kb_listener.start()

            cls._stop_event.clear()
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
    def getRuna(cls):
        # A assinatura do callback de on_click do pynput é (x, y, button, pressed)
        # Aceitamos os quatro parâmetros para evitar TypeError em algumas versões.
        def _on_click(x, y, button, pressed):
            if pressed:
                coords['x'], coords['y'] = int(x), int(y)
                return False  # stop listener
        try:
            print("Buscando Runa")
            coords = {}
            timeout = 10  # segundos
            
            listener = mouse.Listener(on_click=_on_click)
            listener.start()
            listener.join(timeout)  # aguarda até o clique ou timeout
            listener.stop()    
            if 'x' in coords:
                cls.runaX, cls.runaY = coords['x'], coords['y']
                print(f"Runa encontrada em: X {cls.runaX}, Y {cls.runaY}")
                return True
            else:
                print("Nenhuma coordenada registrada (timeout).")
                return False
        except Exception as e:
            print(f"Erro ao localizar runa: {e}")
        finally:
            pass
    

    @classmethod
    def resetRuna(cls):
        cls.runaX = None
        cls.runaY = None
        print("Coordenadas de runa foram resetadas.")

    @classmethod
    def _run(cls):
        try:   
            pgui.moveTo(cls.runaX, cls.runaY)
            pgui.rightClick()
        finally:
            cls._stop_event.set()
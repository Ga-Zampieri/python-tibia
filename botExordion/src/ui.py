"""Interface: uma tela com um interruptor por módulo e o status ao vivo.

Só esta thread toca em widget. O bot avisa pela fila `events` e o status é relido
periodicamente.
"""
from __future__ import annotations

import logging
import os
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from .app_log import LOG_DIR
from .bot import MODULE_TITLES, MODULES, BotController
from .loot import decode_sprite, destination_of, destinations
from .capture import virtual_screen_bounds

logger = logging.getLogger(__name__)

BG = "#14161a"
CARD = "#1d2026"
CARD_HOVER = "#262a31"
LINE = "#2c3038"
TEXT = "#e8eaed"
MUTED = "#8e94a0"
ACCENT = "#3ddc97"
ACCENT_DARK = "#2fae78"
DANGER = "#e5484d"
BAG = "#e5b64a"

FONT = "Segoe UI"
SIZE = (470, 610)
MINI_SIZE = (340, 48)

MACRO_MODES = {"Normal": "normal", "Self use": "self", "Puxar item": "drag"}
MACRO_LABELS = {value: key for key, value in MACRO_MODES.items()}


def font(size=13, weight="normal"):
    return ctk.CTkFont(family=FONT, size=size, weight=weight)


LOOT_FILES = (("Lista de loot", "*.json"),)
PROFILE_FILES = (("Perfil do Exordion", "*.json"),)


class ExordionApp(ctk.CTk):
    def __init__(self, bot: BotController):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=BG)
        self.bot = bot
        self.title("Exordion")
        self.geometry(f"{SIZE[0]}x{SIZE[1]}")
        self.minsize(*MINI_SIZE)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.pages = {}
        self.rows = {}
        self.current_page = "home"
        self.mini = False
        self.log_open = False
        self._save_job = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._build_header()
        self._build_banner()
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=2, column=0, sticky="nsew", padx=14)
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)
        self._build_footer()
        self._build_mini()
        self._build_pages()

        self._refresh_status()
        self._poll_events()

    # ---------- estrutura ----------

    def _build_header(self):
        self.header = ctk.CTkFrame(self, fg_color="transparent")
        self.header.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 8))
        self.header.columnconfigure(1, weight=1)
        ctk.CTkLabel(self.header, text="Exordion", font=font(18, "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w")
        self.connection = ctk.CTkLabel(self.header, text="", font=font(12), text_color=MUTED, anchor="e")
        self.connection.grid(row=0, column=1, sticky="e", padx=8)
        self._ghost_button(self.header, "Mini", self._toggle_mini, width=48).grid(row=0, column=2, padx=(0, 4))
        self._ghost_button(self.header, "Ajustes", lambda: self._open("settings"), width=64).grid(row=0, column=3)

    def _build_banner(self):
        self.banner = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=8)
        self.banner.columnconfigure(0, weight=1)
        self.banner_label = ctk.CTkLabel(self.banner, text="", font=font(13, "bold"), text_color=BG,
                                         anchor="w", wraplength=340, justify="left")
        self.banner_label.grid(row=0, column=0, sticky="ew", padx=12, pady=8)
        self.banner_button = ctk.CTkButton(self.banner, text="", width=72, height=26, font=font(12),
                                           fg_color=BG, hover_color=CARD, text_color=TEXT)
        self.banner_button.grid(row=0, column=1, padx=8)

    def _build_footer(self):
        self.footer = ctk.CTkFrame(self, fg_color="transparent")
        self.footer.grid(row=3, column=0, sticky="ew", padx=14, pady=(8, 10))
        self.footer.columnconfigure(0, weight=1)
        self.last_log = ctk.CTkLabel(self.footer, text="ESC para tudo · atalhos em Ajustes",
                                     font=font(12), text_color=MUTED, anchor="w")
        self.last_log.grid(row=0, column=0, sticky="ew")
        self._ghost_button(self.footer, "Ver log", self._toggle_log, width=60).grid(row=0, column=1)
        self.log_box = ctk.CTkTextbox(self, height=120, font=ctk.CTkFont(family="Consolas", size=12),
                                      fg_color=CARD, text_color=TEXT, state="disabled")

    def _build_mini(self):
        self.mini_bar = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0)
        self.mini_bar.columnconfigure(0, weight=1)
        self.mini_label = ctk.CTkLabel(self.mini_bar, text="", font=font(12), text_color=TEXT, anchor="w")
        self.mini_label.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        ctk.CTkButton(self.mini_bar, text="Parar", width=54, height=28, font=font(12),
                      fg_color=DANGER, hover_color="#c93a3f", command=self.bot.stop_all).grid(row=0, column=1, padx=4)
        self._ghost_button(self.mini_bar, "Abrir", self._toggle_mini, width=52).grid(row=0, column=2, padx=(0, 6))

    def _build_pages(self):
        for page in self.pages.values():
            page.destroy()
        self.pages = {"home": self._page_home()}
        builders = {
            "training": self._page_training,
            "fishing": self._page_fishing,
            "macros": self._page_macros,
            "loot": self._page_loot,
            "repeater": self._page_repeater,
            "alarm": self._page_alarm,
            "survival": self._page_survival,
            "rune_maker": self._page_rune_maker,
            "settings": self._page_settings,
        }
        for name, builder in builders.items():
            self.pages[name] = builder()
        self._open(self.current_page)

    def _open(self, name):
        for page in self.pages.values():
            page.grid_forget()
        self.current_page = name
        if name == "macros":
            self._fill_macro_list()  # uma captura pode ter terminado com a página fechada
        self.pages[name].grid(row=0, column=0, sticky="nsew")

    # ---------- componentes ----------

    def _ghost_button(self, parent, text, command, width=90):
        return ctk.CTkButton(parent, text=text, command=command, width=width, height=28, font=font(12),
                             fg_color="transparent", hover_color=CARD_HOVER, text_color=MUTED,
                             border_width=1, border_color=LINE)

    def _button(self, parent, text, command):
        return ctk.CTkButton(parent, text=text, command=command, height=32, font=font(13),
                             fg_color=CARD_HOVER, hover_color=LINE, text_color=TEXT)

    def _detail_page(self, title):
        page = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        page.columnconfigure(0, weight=1)
        top = ctk.CTkFrame(page, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._ghost_button(top, "‹ Voltar", lambda: self._open("home"), width=70).pack(side="left")
        ctk.CTkLabel(top, text=title, font=font(15, "bold"), text_color=TEXT).pack(side="left", padx=10)
        return page

    def _section(self, page, title, hint=""):
        card = ctk.CTkFrame(page, fg_color=CARD, corner_radius=10)
        card.grid(row=page.grid_size()[1], column=0, sticky="ew", pady=(0, 8))
        card.columnconfigure((0, 1), weight=1, uniform="half")
        ctk.CTkLabel(card, text=title, font=font(13, "bold"), text_color=TEXT, anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 0 if hint else 6))
        if hint:
            ctk.CTkLabel(card, text=hint, font=font(12), text_color=MUTED, anchor="w",
                         justify="left", wraplength=380).grid(
                row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 6))
        return card

    def _place(self, card, widget, column=0, span=2):
        row = card.grid_size()[1] if column == 0 else card.grid_size()[1] - 1
        widget.grid(row=row, column=column, columnspan=span, sticky="ew", padx=12 if span == 2 else 6, pady=(0, 8))

    def _buttons(self, card, *items):
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.columnconfigure(tuple(range(len(items))), weight=1, uniform="buttons")
        for column, (text, command) in enumerate(items):
            self._button(row, text, command).grid(row=0, column=column, sticky="ew", padx=2)
        self._place(card, row)

    def _save_soon(self):
        if self._save_job is not None:
            self.after_cancel(self._save_job)
        self._save_job = self.after(600, self.bot.save)

    def _field(self, card, label, config, key, cast=str, width=90):
        """Campo ligado direto ao perfil; valor inválido é ignorado até corrigir."""
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.columnconfigure(0, weight=1)
        ctk.CTkLabel(row, text=label, font=font(13), text_color=MUTED, anchor="w").grid(row=0, column=0, sticky="ew")
        var = tk.StringVar(value=str(config[key]))

        def changed(*_):
            try:
                config[key] = cast(var.get().replace(",", ".") if cast is float else var.get())
            except ValueError:
                return
            self._save_soon()

        var.trace_add("write", changed)
        ctk.CTkEntry(row, textvariable=var, width=width, height=30, font=font(13), fg_color=BG,
                     border_color=LINE, text_color=TEXT).grid(row=0, column=1)
        self._place(card, row)

    def _check(self, card, text, config, key):
        var = tk.BooleanVar(value=bool(config[key]))

        def changed():
            config[key] = bool(var.get())
            self.bot.save()

        self._place(card, ctk.CTkCheckBox(card, text=text, variable=var, command=changed, font=font(13),
                                          text_color=TEXT, fg_color=ACCENT, hover_color=ACCENT_DARK,
                                          checkmark_color=BG, border_color=MUTED))

    # ---------- páginas ----------

    def _page_home(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        page.columnconfigure(0, weight=1)
        for index, (name, title) in enumerate(MODULES):
            row = ctk.CTkFrame(page, fg_color=CARD, corner_radius=10)
            row.grid(row=index, column=0, sticky="ew", pady=(0, 6))
            row.columnconfigure(0, weight=1)
            text = ctk.CTkFrame(row, fg_color="transparent")
            text.grid(row=0, column=0, sticky="ew", padx=12, pady=7)
            ctk.CTkLabel(text, text=title, font=font(14, "bold"), text_color=TEXT, anchor="w",
                         height=20).pack(anchor="w")
            detail = ctk.CTkLabel(text, text="", font=font(12), text_color=MUTED, anchor="w", height=18)
            detail.pack(anchor="w")
            if name == "loot":  # age uma vez e termina: não tem estado para ligar
                switch = None
                ctk.CTkButton(row, text="Pegar", width=54, height=28, font=font(12), fg_color=CARD_HOVER,
                              hover_color=LINE, text_color=TEXT,
                              command=lambda: self.bot.set_module("loot", True)).grid(row=0, column=1, padx=(0, 2))
            else:
                switch = ctk.CTkSwitch(row, text="", width=44, progress_color=ACCENT, fg_color=LINE,
                                       button_color=TEXT, button_hover_color="#ffffff")
                switch.configure(command=lambda n=name, s=switch: self._flip(n, s))
                switch.grid(row=0, column=1, padx=(0, 2))
            ctk.CTkButton(row, text="›", width=30, height=30, font=font(18), fg_color="transparent",
                          hover_color=CARD_HOVER, text_color=MUTED,
                          command=lambda n=name: self._open(n)).grid(row=0, column=2, padx=(0, 6))
            self.rows[name] = (switch, detail)
        return page

    def _page_training(self):
        page = self._detail_page("Treino")
        config = self.bot.profile["training"]

        card = self._section(page, "Tipo de criatura")

        def mode_changed(value):
            config["mode"] = "summon" if value == "Summon" else "normal"
            self.bot.save()

        mode = ctk.CTkSegmentedButton(card, values=["Summon", "Normal"], command=mode_changed, font=font(13),
                                      selected_color=ACCENT_DARK, selected_hover_color=ACCENT_DARK,
                                      unselected_color=BG, unselected_hover_color=CARD_HOVER)
        mode.set("Summon" if config["mode"] == "summon" else "Normal")
        self._place(card, mode)

        card = self._section(page, "Battle list", "Fica salva relativa à janela do jogo.")
        self._buttons(card, ("Selecionar região", lambda: self._select_region("battle")),
                      ("Testar captura", self._preview_battle_list))

        card = self._section(
            page, "Nomes permitidos",
            "Com a lista preenchida, o treino só ataca esses nomes e o Alarme avisa de qualquer outro. "
            "Deixe só as criaturas certas na battle list e clique em Aprender.",
        )
        self._buttons(card, ("Aprender visíveis", self.bot.learn_visible_names),
                      ("Limpar", self.bot.clear_allowed_names))
        return page

    def _page_fishing(self):
        page = self._detail_page("Pesca")
        card = self._section(page, "Pontos", "Roda em segundo plano, sem bloquear seu mouse.")
        self._buttons(card, ("Capturar vara", self.bot.capture_rod), ("Capturar águas", self.bot.capture_waters))
        self._buttons(card, ("Resetar pesca", self.bot.reset_fishing))
        return page

    def _page_macros(self):
        page = self._detail_page("Macros")
        profile = self.bot.profile

        card = self._section(page, "Nova macro", "As hotkeys só disparam com o jogo em primeiro plano.")
        key_var = tk.StringVar(value="f5")
        mode_var = tk.StringVar(value="Normal")
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.columnconfigure(1, weight=1)
        ctk.CTkEntry(row, textvariable=key_var, width=70, height=30, font=font(13), fg_color=BG,
                     border_color=LINE, text_color=TEXT).grid(row=0, column=0, padx=(0, 8))
        ctk.CTkSegmentedButton(row, values=list(MACRO_MODES), variable=mode_var, font=font(12),
                               selected_color=ACCENT_DARK, selected_hover_color=ACCENT_DARK,
                               unselected_color=BG, unselected_hover_color=CARD_HOVER).grid(row=0, column=1, sticky="ew")
        self._place(card, row)
        self._buttons(card, ("Capturar", lambda: self.bot.capture_macro(key_var.get(), MACRO_MODES[mode_var.get()])),
                      ("Capturar player", self.bot.capture_player))

        self.macro_list = self._section(page, "Hotkeys salvas")
        self._fill_macro_list()

        card = self._section(page, "Puxar item", "Desligue só se o arrasto não funcionar no seu cliente: "
                                                 "aí ele usa o cursor real e traz o jogo para frente.")
        self._check(card, "Arrastar em segundo plano", profile, "drag_in_background")
        return page

    def _fill_macro_list(self):
        for child in self.macro_list.winfo_children()[1:]:
            child.destroy()
        macros = self.bot.profile["macros"]
        if not macros:
            self._place(self.macro_list, ctk.CTkLabel(self.macro_list, text="Nenhuma ainda.", font=font(12),
                                                      text_color=MUTED, anchor="w"))
        for key, macro in sorted(macros.items()):
            row = ctk.CTkFrame(self.macro_list, fg_color="transparent")
            row.columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=key.upper(), font=font(13, "bold"), text_color=TEXT, width=48,
                         anchor="w").grid(row=0, column=0)
            ctk.CTkLabel(row, text=MACRO_LABELS[macro["mode"]], font=font(12), text_color=MUTED,
                         anchor="w").grid(row=0, column=1, sticky="ew")
            self._ghost_button(row, "Remover", lambda k=key: self._remove_macro(k), width=70).grid(row=0, column=2)
            self._place(self.macro_list, row)

    def _remove_macro(self, key):
        self.bot.remove_macro(key)
        self._fill_macro_list()

    def _page_loot(self):
        page = self._detail_page("Loot")
        card = self._section(page, "Como usar", "Abra o loot e aperte o atalho do Loot, em Ajustes. A cada "
                                                "aperto ele pega os itens aprendidos, abre as bags, fecha a "
                                                "janela e termina. Não precisa ligar nada.")
        card = self._section(page, "Slots", "Abra um container e selecione só a área dos itens. "
                                            "O loot precisa abrir sempre nesse mesmo lugar.")
        self._buttons(card, ("Selecionar slots", lambda: self._select_region("loot")),
                      ("Testar leitura", self._preview_loot))
        self.loot_targets = self._section(page, "Destinos", "Clique na mochila que recebe os itens. Tudo vai "
                                                            "para a BP 1, até você trocar em Aprendidos.")
        card = self._section(page, "Fechar ao terminar", "Clique no X da janela do loot. Ela só fecha se tudo "
                                                         "correr bem.")
        self._buttons(card, ("Capturar X", self.bot.capture_loot_close), ("Não fechar", self.bot.clear_loot_close))

        card = self._section(page, "Aprender", "Deixe nos slots só o que quer ensinar e clique no botão. "
                                               "Pilhas mudam de desenho conforme a quantidade: "
                                               "ensine cada tamanho, como no ouro.")
        self._buttons(card, ("Aprender itens", lambda: self.bot.learn_loot("items")),
                      ("Aprender bags", lambda: self.bot.learn_loot("bags")))

        self.loot_list = self._section(page, "Aprendidos", "Clique em um desenho para trocar a BP ou remover.")
        self._fill_loot()

        card = self._section(page, "Compartilhar", "A lista leva itens, bags e o número da BP. Quem importa soma à "
                                                   "própria lista e mantém slots, destinos e X.")
        self._buttons(card, ("Exportar lista", self._export_loot), ("Importar lista", self._import_loot))
        return page

    def _export_loot(self):
        path = filedialog.asksaveasfilename(parent=self, title="Exportar lista de loot", defaultextension=".json",
                                            initialfile="loot-exordion.json", filetypes=LOOT_FILES)
        if path:
            self.bot.export_loot(path)

    def _import_loot(self):
        path = filedialog.askopenfilename(parent=self, title="Importar lista de loot", filetypes=LOOT_FILES)
        if path:
            self.bot.import_loot(path)

    def _fill_loot(self):
        for card in (self.loot_targets, self.loot_list):
            for child in card.winfo_children()[2:]:  # mantém título e dica
                child.destroy()
        config = self.bot.profile["loot"]
        targets = destinations(config)
        for index, point in enumerate(targets):
            self._loot_target(index, point)
        self._buttons(self.loot_targets, ("Adicionar BP", lambda: self.bot.capture_loot_destination(len(targets))))

        for target in range(len(targets)):
            items = [(index, sprite) for index, sprite in enumerate(config["items"])
                     if destination_of(config, sprite) == target]
            self._loot_group(f"BP {target + 1}: {len(items)} item(ns)", items, self._item_menu)
        self._loot_group(f"Bags, que só são abertas: {len(config['bags'])}", list(enumerate(config["bags"])),
                         self._bag_menu)

    def _loot_target(self, index, point):
        row = ctk.CTkFrame(self.loot_targets, fg_color="transparent")
        row.columnconfigure(0, weight=1)
        ctk.CTkLabel(row, text=f"BP {index + 1}" if point else f"BP {index + 1}: falta capturar", font=font(13),
                     text_color=TEXT if point else MUTED, anchor="w").grid(row=0, column=0, sticky="ew")
        capture = self._button(row, "Capturar", lambda: self.bot.capture_loot_destination(index))
        capture.configure(width=86)
        capture.grid(row=0, column=1, padx=2)
        if index:
            remove = self._button(row, "Remover", lambda: self.bot.remove_loot_destination(index))
            remove.configure(width=86)
            remove.grid(row=0, column=2, padx=2)
        self._place(self.loot_targets, row)

    def _loot_group(self, title, entries, on_click):
        self._place(self.loot_list, ctk.CTkLabel(self.loot_list, text=title, font=font(12), text_color=MUTED,
                                                 anchor="w"))
        if not entries:
            return
        grid = ctk.CTkFrame(self.loot_list, fg_color="transparent")
        for position, (index, sprite) in enumerate(entries):
            image = ctk.CTkImage(Image.fromarray(decode_sprite(sprite)), size=(32, 32))
            ctk.CTkButton(grid, text="", image=image, width=40, height=40, fg_color=BG, hover_color=LINE,
                          command=lambda i=index: on_click(i)).grid(
                row=position // 8, column=position % 8, padx=2, pady=2)
        self._place(self.loot_list, grid)

    def _popup(self, entries):
        menu = tk.Menu(self, tearoff=0, bg=CARD, fg=TEXT, activebackground=LINE, activeforeground=TEXT,
                       disabledforeground=MUTED, bd=0)
        for label, command in entries:
            menu.add_command(label=label, command=command, state="normal" if command else "disabled")
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        menu.grab_release()

    def _item_menu(self, item):
        config = self.bot.profile["loot"]
        current = destination_of(config, config["items"][item])
        entries = [(f"Enviar para BP {target + 1}" if target != current else f"Vai para BP {target + 1}",
                    (lambda t=target: self.bot.route_loot(item, t)) if target != current else None)
                   for target in range(len(destinations(config)))]
        self._popup(entries + [("Remover", lambda: self.bot.remove_loot("items", item))])

    def _bag_menu(self, bag):
        self._popup([("Remover", lambda: self.bot.remove_loot("bags", bag))])

    def _page_repeater(self):
        page = self._detail_page("Repetidor")
        card = self._section(
            page, "Repetir",
            "Se a tecla for uma macro salva, ela roda direto, mesmo com o jogo atrás. "
            "Senão, a tecla é enviada só para a janela do jogo.",
        )
        config = self.bot.profile["repeater"]
        self._field(card, "Tecla", config, "key", lambda v: v.strip().lower())
        self._field(card, "Intervalo (s)", config, "interval", float)
        return page

    def _page_alarm(self):
        page = self._detail_page("Alarme")
        card = self._section(
            page, "Quando dispara",
            "Com nomes permitidos (em Treino): qualquer nome de fora. Sem eles: quando a battle list "
            "fica maior do que estava ao ligar o alarme.",
        )
        config = self.bot.profile["alarm"]
        self._check(card, "Tocar som", config, "sound")
        self._check(card, "Parar treino, pesca, repetidor e rune maker", config, "pause_modules")
        return page

    def _page_survival(self):
        page = self._detail_page("Sobrevivência")
        config = self.bot.profile["survival"]

        card = self._section(page, "Comer")
        self._check(card, "Comer automaticamente", config["eat"], "enabled")
        self._field(card, "Intervalo (s)", config["eat"], "interval", float)
        self._buttons(card, ("Capturar comida", self.bot.capture_food))

        card = self._section(page, "Anti-idle", "Vira o personagem para não ser desconectado.")
        self._check(card, "Ativar anti-idle", config["anti_idle"], "enabled")
        self._field(card, "Intervalo (s)", config["anti_idle"], "interval", float)

        card = self._section(page, "Barras", "Selecione cada barra cheia, de ponta a ponta.")
        self._buttons(card, ("Selecionar HP", lambda: self._select_region("hp_bar")),
                      ("Selecionar mana", lambda: self._select_region("mana_bar")))

        card = self._section(
            page, "Regras",
            "A ação pode ser uma macro salva, uma tecla ou uma magia (ex.: exura).",
        )
        for rule in config["rules"]:
            self._rule_row(card, rule)
        return page

    def _rule_row(self, card, rule):
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.columnconfigure(4, weight=1)
        enabled = tk.BooleanVar(value=bool(rule["enabled"]))

        def toggled():
            rule["enabled"] = bool(enabled.get())
            self.bot.save()

        ctk.CTkCheckBox(row, text="", width=24, variable=enabled, command=toggled, fg_color=ACCENT,
                        hover_color=ACCENT_DARK, checkmark_color=BG, border_color=MUTED).grid(row=0, column=0)

        def menu(column, values, key, width):
            def changed(value):
                rule[key] = value.lower()
                self.bot.save()
            widget = ctk.CTkOptionMenu(row, values=values, command=changed, width=width, height=30, font=font(12),
                                       fg_color=BG, button_color=LINE, button_hover_color=CARD_HOVER)
            widget.set(rule[key].upper() if key == "stat" else rule[key])
            widget.grid(row=0, column=column, padx=2)

        menu(1, ["HP", "MANA"], "stat", 74)
        menu(2, ["<", ">"], "op", 50)

        def entry(column, key, width, cast, placeholder=""):
            var = tk.StringVar(value=str(rule[key]))

            def changed(*_):
                try:
                    rule[key] = cast(var.get())
                except ValueError:
                    return
                self._save_soon()

            var.trace_add("write", changed)
            widget = ctk.CTkEntry(row, textvariable=var, width=width, height=30, font=font(12), fg_color=BG,
                                  border_color=LINE, text_color=TEXT, placeholder_text=placeholder)
            widget.grid(row=0, column=column, padx=2, sticky="ew")

        entry(3, "percent", 44, float)
        entry(4, "action", 90, str.strip)
        self._place(card, row)

    def _page_rune_maker(self):
        page = self._detail_page("Rune Maker")
        config = self.bot.profile["rune_maker"]
        capture = self.bot.capture_rune_maker
        card = self._section(page, "Pontos", "A mão precisa estar livre. As blank runes ficam sempre no mesmo slot. "
                                                 "Se a blank não chegar na mão, ele para e avisa.")
        self._buttons(card, ("Blank rune", lambda: capture("blank", "blank rune")),
                      ("Mão", lambda: capture("hand", "mão")),
                      ("Destino", lambda: capture("output", "destino")))
        card = self._section(page, "Conjuração", "Com a barra de mana selecionada, espera a mana mínima.")
        self._field(card, "Magia", config, "spell", str.strip, width=150)
        self._field(card, "Mana mínima (%)", config, "mana_percent", float)
        self._field(card, "Intervalo (s)", config, "interval", float)
        self._field(card, "Espera da magia (s)", config, "cast_wait", float)
        return page

    def _page_settings(self):
        page = self._detail_page("Ajustes")

        card = self._section(page, "Janela do jogo", "O bot acha o Tibia sozinho. Escolha aqui se ele não achar.")
        self.window_menu = ctk.CTkOptionMenu(card, values=["Clique em Atualizar"], height=30, font=font(12),
                                             fg_color=BG, button_color=LINE, button_hover_color=CARD_HOVER,
                                             dynamic_resizing=False)
        self._place(card, self.window_menu)
        self._buttons(card, ("Atualizar", self._refresh_windows), ("Conectar", self._connect_window))

        card = self._section(page, "Perfil", "Cada perfil guarda toda a configuração de um personagem.")
        self.profile_menu = ctk.CTkOptionMenu(card, values=self.bot.store.names() or [self.bot.profile_name],
                                              command=self._switch_profile, height=30, font=font(12),
                                              fg_color=BG, button_color=LINE, button_hover_color=CARD_HOVER)
        self.profile_menu.set(self.bot.profile_name)
        self._place(card, self.profile_menu)
        self._buttons(card, ("Novo", self._new_profile), ("Renomear", self._rename_profile),
                      ("Apagar", self._delete_profile))
        self._buttons(card, ("Exportar perfil", self._export_profile), ("Importar perfil", self._import_profile))

        self.hotkey_list = self._section(
            page, "Atalhos",
            "Ligam e desligam o módulo em qualquer janela; o Loot só age com o jogo na frente. "
            "Vale Ctrl, Alt e Shift. ESC sempre para tudo.",
        )
        self._fill_hotkeys()

        card = self._section(page, "Diagnóstico")
        self._buttons(card, ("Abrir pasta de logs", lambda: os.startfile(LOG_DIR)))
        return page

    def _fill_hotkeys(self):
        for child in self.hotkey_list.winfo_children()[2:]:  # mantém título e dica
            child.destroy()
        hotkeys = self.bot.profile["module_hotkeys"]
        for name, title in MODULES:
            row = ctk.CTkFrame(self.hotkey_list, fg_color="transparent")
            row.columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=title, font=font(13), text_color=TEXT, anchor="w").grid(
                row=0, column=0, sticky="ew")
            self._ghost_button(row, hotkeys[name].upper() or "Definir",
                               lambda n=name: self.bot.capture_module_hotkey(n), width=120).grid(row=0, column=1)
            if hotkeys[name]:
                self._ghost_button(row, "Limpar", lambda n=name: self.bot.clear_module_hotkey(n),
                                   width=60).grid(row=0, column=2, padx=(4, 0))
            self._place(self.hotkey_list, row)

    # ---------- ações da interface ----------

    def _flip(self, name, switch):
        if not self.bot.set_module(name, bool(switch.get())):
            switch.deselect()

    def _refresh_windows(self):
        self.window_map = {f"{title} ({hwnd})": hwnd for title, hwnd in self.bot.list_windows()}
        values = list(self.window_map) or ["Nenhuma janela"]
        self.window_menu.configure(values=values)
        self.window_menu.set(values[0])

    def _connect_window(self):
        hwnd = getattr(self, "window_map", {}).get(self.window_menu.get())
        if hwnd is not None:
            self.bot.attach(hwnd)

    def _switch_profile(self, name):
        self.bot.switch_profile(name)
        self.current_page = "settings"
        self._build_pages()

    def _new_profile(self):
        name = ctk.CTkInputDialog(text="Nome do novo perfil:", title="Novo perfil").get_input()
        if name and name.strip():
            self.bot.create_profile(name)
            self.current_page = "settings"
            self._build_pages()

    def _rename_profile(self):
        name = ctk.CTkInputDialog(text=f"Novo nome para {self.bot.profile_name}:", title="Renomear perfil").get_input()
        if name and self.bot.rename_profile(name):
            self.current_page = "settings"
            self._build_pages()

    def _export_profile(self):
        path = filedialog.asksaveasfilename(parent=self, title="Exportar perfil", defaultextension=".json",
                                            initialfile=f"perfil-{self.bot.profile_name}.json", filetypes=PROFILE_FILES)
        if path:
            self.bot.export_profile(path)

    def _import_profile(self):
        path = filedialog.askopenfilename(parent=self, title="Importar perfil", filetypes=PROFILE_FILES)
        if path and self.bot.import_profile(path):
            self.current_page = "settings"
            self._build_pages()

    def _delete_profile(self):
        if self.bot.delete_profile():
            self.current_page = "settings"
            self._build_pages()

    def _select_region(self, target):
        left, top, width, height = virtual_screen_bounds()
        overlay = tk.Toplevel(self)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.3)
        overlay.geometry(f"{width}x{height}{left:+d}{top:+d}")
        canvas = tk.Canvas(overlay, cursor="crosshair", bg="black", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        start = {}

        def press(event):
            start.update(x=event.x_root, y=event.y_root)
            start["id"] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline=ACCENT, width=2)

        def move(event):
            if "id" in start:
                canvas.coords(start["id"], start["x"] - left, start["y"] - top, event.x, event.y)

        def release(event):
            overlay.destroy()
            if "id" in start:
                self.bot.set_region_from_screen(target, (
                    min(start["x"], event.x_root), min(start["y"], event.y_root),
                    abs(event.x_root - start["x"]), abs(event.y_root - start["y"]),
                ))

        canvas.bind("<ButtonPress-1>", press)
        canvas.bind("<B1-Motion>", move)
        canvas.bind("<ButtonRelease-1>", release)
        canvas.bind("<ButtonPress-3>", lambda _event: overlay.destroy())
        overlay.bind("<Escape>", lambda _event: overlay.destroy())
        overlay.focus_force()

    def _preview_battle_list(self):
        pixels, snapshot = self.bot.test_capture()
        if pixels is None:
            return
        image = Image.fromarray(pixels)
        left, top = self.bot.profile["training"]["region"][:2]
        draw = ImageDraw.Draw(image)
        for row in snapshot.rows:
            color = ACCENT if row.allowed else DANGER
            draw.rectangle((row.bounds[0] - left, row.bounds[1] - top,
                            row.bounds[2] - left - 1, row.bounds[3] - top - 1), outline=color)
        self._show_preview(image, "Prévia da battle list")

    def _preview_loot(self):
        pixels, slots = self.bot.test_loot()
        if pixels is None:
            return
        image = Image.fromarray(pixels)
        draw = ImageDraw.Draw(image)
        colors = {"item": ACCENT, "bag": BAG, "other": DANGER, None: MUTED}
        for x, y, kind in slots:
            draw.rectangle((x, y, x + 31, y + 31), outline=colors[kind])
        self._show_preview(image, "Prévia do loot")

    def _show_preview(self, image, title):
        window = tk.Toplevel(self)
        window.title(title)
        window.attributes("-topmost", True)
        photo = ImageTk.PhotoImage(image)
        label = tk.Label(window, image=photo)
        label.image = photo
        label.pack(padx=8, pady=8)

    def _toggle_log(self):
        self.log_open = not self.log_open
        if self.log_open:
            self.log_box.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 10))
            self.geometry(f"{SIZE[0]}x{SIZE[1] + 130}")
        else:
            self.log_box.grid_forget()
            self.geometry(f"{SIZE[0]}x{SIZE[1]}")

    def _toggle_mini(self):
        self.mini = not self.mini
        widgets = (self.header, self.content, self.footer)
        if self.mini:
            for widget in widgets:
                widget.grid_remove()
            self.log_box.grid_forget()
            self.log_open = False
            self.mini_bar.grid(row=2, column=0, sticky="nsew")
            self.attributes("-topmost", True)
            self.geometry(f"{MINI_SIZE[0]}x{MINI_SIZE[1]}")
        else:
            self.mini_bar.grid_forget()
            for widget in widgets:
                widget.grid()
            self.attributes("-topmost", False)
            self.geometry(f"{SIZE[0]}x{SIZE[1]}")

    def _show_banner(self, text, color, button_text, command):
        self.banner.configure(fg_color=color)
        self.banner_label.configure(text=text)
        self.banner_button.configure(text=button_text, command=command)
        self.banner.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))

    # ---------- atualização ----------

    def _append_log(self, message):
        self.last_log.configure(text=message if len(message) <= 56 else message[:55] + "…")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _poll_events(self):
        while not self.bot.events.empty():
            kind, payload = self.bot.events.get_nowait()
            if kind == "log":
                self._append_log(payload)
                if self.current_page == "macros" and payload.startswith("Macro"):
                    self._fill_macro_list()
            elif kind == "prompt":
                if payload is None:
                    self.banner.grid_forget()
                else:
                    self._show_banner(payload, ACCENT, "Cancelar", self.bot.cancel_capture)
            elif kind == "hotkeys":
                self._fill_hotkeys()
            elif kind == "loot":
                self._fill_loot()
            elif kind == "alarm":
                self._show_banner(f"ALARME: {payload}", DANGER, "OK", self.banner.grid_forget)
                self.deiconify()
                self.lift()
        self.after(120, self._poll_events)

    def _refresh_status(self):
        status = self.bot.status()
        if status["connected"]:
            title = status["title"]
            self.connection.configure(text=f"● {title[:26]}", text_color=ACCENT)
        else:
            self.connection.configure(text="○ Jogo não encontrado", text_color=MUTED)

        active = []
        for name, (switch, detail) in self.rows.items():
            on, text = status[name]
            detail.configure(text=text)
            if on:
                active.append(MODULE_TITLES[name])
            if switch is not None and bool(switch.get()) != on:
                switch.select() if on else switch.deselect()
        self.mini_label.configure(text=" · ".join(active) or "Nada ligado")
        self.after(500, self._refresh_status)

    def _close(self):
        self.bot.shutdown()
        self.destroy()


def run_ui() -> None:
    bot = BotController()
    app = ExordionApp(bot)
    bot.start()
    app.report_callback_exception = lambda *exc: logger.error("Erro na interface", exc_info=exc)
    app.mainloop()

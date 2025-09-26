from curl_cffi import requests
from bs4 import BeautifulSoup
import utils.utils as u

SLOTS_WANDS_E_RODS = ["Wands", "Rods"]

WIKI_URL = "https://www.tibiawiki.com.br/wiki/{}"
SLOTS_ITENS_URLS = [WIKI_URL.format(slot) for slot in SLOTS_WANDS_E_RODS]

class WandsERods:
    def __init__(self, type, id, name, level, vocations, tipoDano, bonus, protection, danoMedio, manaPorAtaque, peso, precoComprarDoNPC, precoVenderParaNPC):
        self.type = type
        self.id = id
        self.name = name
        self.level = level
        self.vocations = vocations
        self.tipoDano = tipoDano
        self.bonus = bonus
        self.protection = protection
        self.danoMedio = danoMedio
        self.manaPorAtaque = manaPorAtaque
        self.peso = peso
        self.precoComprarDoNPC = precoComprarDoNPC
        self.precoVenderParaNPC = precoVenderParaNPC

    def __str__(self):
        return (f"Item: {self.name}, Level: {self.level}, Peso: {self.peso}\n"
                f"Vocações: {self.vocations}, Tipo de Dano: {self.tipoDano}\n"
                f"Bônus: {self.bonus}, Proteção: {self.protection}\n"
                f"Dano Médio: {self.danoMedio}, Mana por Ataque: {self.manaPorAtaque}\n"
                f"Comprar do NPC: {self.precoComprarDoNPC}, Vender para NPC: {self.precoVenderParaNPC}\n"
                "---------------------------------------- \n"
        )
    def __repr__(self):
        return self.__str__()
    

    
def getInfosFromItensWiki(ITEMS_WIKI):
    for url in SLOTS_ITENS_URLS:
        response = requests.get(
            url,
            impersonate="chrome110",
            timeout=30
        )
        item_type = url.split("/")[-1].replace('_', ' ')
        if response.status_code != 200:
            print(f"Erro ao acessar a URL: {url}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        # Procura a tabela de itens
        table = soup.find("table", {"id": "tabelaDPL"})
        if not table:
            print(f"Nenhuma tabela encontrada na URL: {url}")
            continue

        for row in table.find_all("tr")[1:]:  # Pula o cabeçalho
            cols = row.find_all("td")
            if len(cols) >= 2:
                item_name = cols[0].get_text(strip=True)
                item_link = WIKI_URL.format(item_name.replace(' ', '_'))
                item_level = cols[2].get_text(strip=True)
                item_vocations = cols[3].get_text(strip=False).replace('\n', ' ').strip()
                item_tipoDano = cols[4].get_text(strip=True)
                item_bonus = cols[5].get_text(strip=True)
                item_protection = cols[6].get_text(strip=True)
                item_danoMedio = cols[7].get_text(strip=True)
                item_manaPorAtaque = cols[8].get_text(strip=True)
                item_peso = cols[11].get_text(strip=True)

            
            response = requests.get(
                item_link,
                impersonate="chrome110",
                timeout=30
            )
            if response.status_code != 200:
                print(f"Erro ao acessar a URL: {url}")
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            
            precoComprarDoNPC = u.get_buy_price(soup)
            precoVenderParaNPC = u.get_sell_price(soup)

            item = WandsERods(
                    item_type,
                    None, #item_id
                    item_name,
                    item_level,
                    item_vocations,
                    item_tipoDano,
                    item_bonus,
                    item_protection,
                    item_danoMedio,
                    item_manaPorAtaque,
                    item_peso,
                    precoComprarDoNPC,
                    precoVenderParaNPC
                )
            ITEMS_WIKI.append(item)
            print(item.__str__())
from curl_cffi import requests
from bs4 import BeautifulSoup
import utils.Utils as u

SLOTS_ESCUDOS_SPELLBOOKS = ["Spellbooks", "Escudos"]
WIKI_URL = "https://www.tibiawiki.com.br/wiki/{}"
SLOTS_ITENS_URLS = [WIKI_URL.format(slot) for slot in SLOTS_ESCUDOS_SPELLBOOKS]

class AljavaEscudosSpellbooks:
    def __init__(self, type, id, name, level, vocation, defesa, bonus, protection, peso, precoComprarDoNPC, precoVenderParaNPC):
        self.type = type
        self.id = id
        self.name = name
        self.level = level
        self.vocation = vocation
        self.defesa = defesa
        self.bonus = bonus
        self.protection = protection
        self.peso = peso
        self.precoComprarDoNPC = precoComprarDoNPC
        self.precoVenderParaNPC = precoVenderParaNPC

    def __str__(self):
        return (f"Item: {self.name}, Level: {self.level}, Peso: {self.peso}\n"
                f"Vocações: {self.vocation}, Defesa: {self.defesa}\n"
                f"Protection: {self.protection}, Bônus: {self.bonus}\n"
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
            if item_type == "Escudos":
                item_name = cols[0].get_text(strip=True)
                item_link = WIKI_URL.format(item_name.replace(' ', '_'))
                item_level = cols[2].get_text(strip=True)
                item_vocation = cols[3].get_text(strip=True)
                item_defesa = cols[5].get_text(strip=True)
                item_bonus = cols[6].get_text(strip=True)
                item_protection = cols[7].get_text(strip=True)
                item_peso = cols[8].get_text(strip=True)
            else:  # Spellbooks
                item_name = cols[0].get_text(strip=True)
                item_link = WIKI_URL.format(item_name.replace(' ', '_'))
                item_level = cols[2].get_text(strip=True)
                item_vocation = cols[3].get_text(strip=True)
                item_defesa = cols[4].get_text(strip=True)
                item_bonus = cols[5].get_text(strip=True)
                item_protection = cols[6].get_text(strip=True)
                item_peso = cols[8].get_text(strip=True)

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

            item = AljavaEscudosSpellbooks(
                    item_type,
                    None, #item_id
                    item_name,
                    item_level,
                    item_vocation,
                    item_defesa,
                    item_bonus,
                    item_protection,
                    item_peso,
                    precoComprarDoNPC,
                    precoVenderParaNPC
                )
            ITEMS_WIKI.append(item)
            print(item.__str__())
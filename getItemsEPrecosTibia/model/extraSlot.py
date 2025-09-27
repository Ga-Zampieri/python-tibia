from curl_cffi import requests
from bs4 import BeautifulSoup
import utils.Utils as u

SLOTS_EXTRA_SLOT = ["Extra Slot"]
WIKI_URL = "https://www.tibiawiki.com.br/wiki/{}"
SLOTS_ITENS_URLS = [WIKI_URL.format(slot) for slot in SLOTS_EXTRA_SLOT]

class ExtraSlot:
    def __init__(self, type, id, name, atributos, peso, precoComprarDoNPC, precoVenderParaNPC):
        self.type = type
        self.id = id
        self.name = name
        self.atributos = atributos
        self.peso = peso
        self.precoComprarDoNPC = precoComprarDoNPC
        self.precoVenderParaNPC = precoVenderParaNPC

    def __str__(self):
        return (f"Item: {self.name}, Atributos: {self.atributos}, Peso: {self.peso}\n"
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
            if len(cols) >= 3:
                item_name = cols[0].get_text(strip=True)
                item_link = WIKI_URL.format(item_name.replace(' ', '_'))
                item_atributos = cols[2].get_text(strip=True)
                item_peso = cols[3].get_text(strip=True)

            
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

            item = ExtraSlot(
                    item_type,
                    None, #item_id
                    item_name,
                    item_atributos,
                    item_peso,
                    precoComprarDoNPC,
                    precoVenderParaNPC
                )
            ITEMS_WIKI.append(item)
            print(item.__str__())
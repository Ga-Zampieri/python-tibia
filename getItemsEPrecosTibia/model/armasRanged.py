from curl_cffi import requests
from bs4 import BeautifulSoup
import utils.utils as u

SLOTS_ARMAS_RANGED = ["Distância"]
WIKI_URL = "https://www.tibiawiki.com.br/wiki/{}"
SLOTS_ITENS_URLS = [WIKI_URL.format(slot) for slot in SLOTS_ARMAS_RANGED]

class ArmaRange:
    def __init__(self, type, id, name, level, vocations, maos, alcance, atk, hit, bonus, atkElemental, protection, peso, precoComprarDoNPC, precoVenderParaNPC):
        self.type = type
        self.id = id
        self.name = name
        self.level = level
        self.vocations = vocations
        self.maos = maos
        self.alcance = alcance
        self.atk = atk
        self.hit = hit
        self.bonus = bonus
        self.atkElemental = atkElemental
        self.protection = protection
        self.peso = peso
        self.precoComprarDoNPC = precoComprarDoNPC
        self.precoVenderParaNPC = precoVenderParaNPC

    def __str__(self):
        return (f"Item: {self.name}, Level: {self.level}, Peso: {self.peso}\n"
                f"Vocações: {self.vocations}, Mãos: {self.maos}\n"
                f"Ataque: {self.atk}, Ataque Elemental: {self.atkElemental}, Alcance: {self.alcance}, Hit: {self.hit} \n"
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
        tables = soup.find_all("table", {"id": "tabelaDPL"}) 
        for table in tables:
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
                    item_maos = cols[4].get_text(strip=True)
                    item_alcance = cols[5].get_text(strip=True)
                    item_atk = cols[6].get_text(strip=True)
                    item_hit = cols[7].get_text(strip=True)
                    item_bonus = cols[8].get_text(strip=True)
                    item_atkElemental = cols[9].get_text(strip=True)
                    item_protection = cols[10].get_text(strip=True)
                    item_peso = cols[13].get_text(strip=True)

            
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

                item = ArmaRange(
                        item_type,
                        None, #item_id
                        item_name,
                        item_level,
                        item_vocations,
                        item_maos,
                        item_alcance,
                        item_atk,
                        item_hit,
                        item_bonus,
                        item_atkElemental,
                        item_protection,
                        item_peso,
                        precoComprarDoNPC,
                        precoVenderParaNPC
                    )
                ITEMS_WIKI.append(item)
                print(item.__str__())
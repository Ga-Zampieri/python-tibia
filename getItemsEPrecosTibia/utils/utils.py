import re
import xml.etree.ElementTree as ET

def get_sell_price(soup):
    tables = soup.find(text="Vende para:").find_next("tr").find_all("td")
    tabela_venda = None
    for i in range(len(tables)):
        texto = tables[i].text.strip()
        if texto == "Jogadores.":
            continue
        if i == 1:
            tabela_venda = tables[1]
    if tabela_venda is None:
        return None
    
    tabela_venda = tabela_venda.find_next("table")
    if len(tabela_venda.contents) == 1:
        return None
    sell_prices = []

    for row in tabela_venda.find_all("tr")[1:]:
        cols = row.find_all("td")
        if len(cols) >= 3:
            price_text = cols[2].get_text(strip=True)
            if "crystalline token" in price_text.lower():
                price = re.sub(r"[^\d]", "", price_text)
                price = str(int(price) * 1000000)
            elif "gold token" in price_text.lower():
                price = re.sub(r"[^\d]", "", price_text)
                price = str(int(price) * 100000)
            elif "silver token" in price_text.lower():
                price = re.sub(r"[^\d]", "", price_text)
                price = str(int(price) * 10000)
            else:
                price = re.sub(r"[^\d]", "", price_text)
            if price.isdigit():
                sell_prices.append(int(price))
    if sell_prices:
        return max(sell_prices)
    
def get_buy_price(soup):
    tables = soup.find(text="Compra de:").find_next("tr").find_all("td")
    tabela_compra = None
    for i in range(len(tables)):
        texto = tables[i].text.strip()
        if texto == "Jogadores.":
            continue
        if i == 0:
            tabela_compra = tables[0]
            
    if tabela_compra is None:
        return None
    
    tabela_compra = tabela_compra.find_next("table")
    if len(tabela_compra.contents) == 1:
        return None
    buy_prices = []

    for row in tabela_compra.find_all("tr")[1:]:
        cols = row.find_all("td")
        if len(cols) >= 3:
            price_text = cols[2].get_text(strip=True)
            if "crystalline token" in price_text.lower():
                price = re.sub(r"[^\d]", "", price_text)
                price = str(int(price) * 1000000)
            elif "gold token" in price_text.lower():
                price = re.sub(r"[^\d]", "", price_text)
                price = str(int(price) * 100000)
            elif "silver token" in price_text.lower():
                price = re.sub(r"[^\d]", "", price_text)
                price = str(int(price) * 10000)
            else:
                price = re.sub(r"[^\d]", "", price_text)
            if price.isdigit():
                buy_prices.append(int(price))
    if buy_prices:
        return max(buy_prices)

def addBuyableFunction(item_list):
    itens_compraveis = []
    item_type = None
    for item in item_list:
        if item.precoComprarDoNPC is None:
            continue
        if (item.type is not None and item.type != item_type):
            item_type = item.type
            itens_compraveis.append(f"------------------------------------SLOT: {item_type}------------------------------------\n")
        itens_compraveis.append(f"shopModule:addBuyableItem({{'{item.name}'}}, {item.id}, {item.precoComprarDoNPC}, 0, '{item.name}')\n")
    return itens_compraveis

def addSellableFunction(item_list):
    itens_vendiveis = []
    item_type = None
    for item in item_list:
        if item.precoVenderParaNPC is None:
            continue
        if (item.type is not None and item.type != item_type):
            item_type = item.type
            itens_vendiveis.append(f"------------------------------------SLOT: {item_type}------------------------------------\n")
        itens_vendiveis.append(f"shopModule:addSellableItem({{'{item.name}'}}, {item.id}, {item.precoVenderParaNPC})\n")
    return itens_vendiveis

def getIdFromXML(xml_file, item_list):
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        
        item_dict = {}
        
        for item in root.findall('.//item'):
            name = item.get('name')
            item_id = item.get('id')
            if name and item_id:
                if name.lower() in item_dict:
                    continue
                else:
                    item_dict[name.lower()] = (name, item_id)

        # Depois busca cada item da lista no dicionário
        for item in item_list:
            normalized_name = item.name.lower()
            if normalized_name in item_dict:
                name, item_id = item_dict[normalized_name]
                item.id = item_id
    

    except FileNotFoundError:
        return ["Arquivo XML não encontrado."]
    except ET.ParseError:
        return ["Erro ao analisar o arquivo XML."]
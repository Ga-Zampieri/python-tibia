import utils.Utils as u

import model.Item as it
import model.ArmasRanged as ar
import model.ArmasMelee as am
import model.WandsERods as wr
import model.Municao as mu
import model.AljavasEscudosSpellbooks as al
import model.CreatureProductsEValiosos as cp
import model.AmuletosColaresAneis as aca
import model.ExtraSlot as ex


ITEMS_WIKI = []
ITEMS_VENDIVEIS = []
ITEMS_COMPRAVEIS = []
OUTPUT_FILE = "C:\\Git\\python\\python-tibia\\getItemsEPrecosTibia\\assets\\output.txt"
OUTPUT_ITENS_COMPRAVEIS = "C:\\Git\\python\\python-tibia\\getItemsEPrecosTibia\\assets\\output_compraveis.txt"
OUTPUT_ITENS_VENDIVEIS = "C:\\Git\\python\\python-tibia\\getItemsEPrecosTibia\\assets\\output_vendiveis.txt"
XML_FILE = "C:\\Git\\python\\python-tibia\\getItemsEPrecosTibia\\assets\\items.xml"

def main():

    # ex.getInfosFromItensWiki(ITEMS_WIKI)
    it.getInfosFromItensWiki(ITEMS_WIKI)
    am.getInfosFromItensWiki(ITEMS_WIKI)
    ar.getInfosFromItensWiki(ITEMS_WIKI)
    mu.getInfosFromItensWiki(ITEMS_WIKI)
    al.getInfosFromItensWiki(ITEMS_WIKI)
    wr.getInfosFromItensWiki(ITEMS_WIKI)
    cp.getInfosFromItensWiki(ITEMS_WIKI)
    aca.getInfosFromItensWiki(ITEMS_WIKI)

    u.getIdFromXML(XML_FILE, ITEMS_WIKI)

    ITEMS_VENDIVEIS = u.addSellableFunction(ITEMS_WIKI)
    ITEMS_COMPRAVEIS = u.addBuyableFunction(ITEMS_WIKI)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        item_type = None
        f.write(f"{ITEMS_WIKI.count} itens.")
        for item in ITEMS_WIKI:
            if (item_type is None) or item_type != item.type:
                item_type = item.type
                f.write(f"-----------------Slot: " + item.type + "-----------------\n")
            f.write(item.__repr__())
        print("Finalizada escrita de itens gerais.")


    with open(OUTPUT_ITENS_COMPRAVEIS, "w", encoding="utf-8") as f:
        f.write(f"{ITEMS_COMPRAVEIS.count} itens compráveis.")
        for item in ITEMS_COMPRAVEIS:
            f.write(item)
        print("Finalizada escrita de itens compráveis.")

    with open(OUTPUT_ITENS_VENDIVEIS, "w", encoding="utf-8") as f:
        f.write(f"{ITEMS_COMPRAVEIS.count} itens vendíveis.")
        for item in ITEMS_VENDIVEIS:
            f.write(item)
        print("Finalizada escrita de itens vendíveis.")
    
if __name__ == "__main__":
    main()
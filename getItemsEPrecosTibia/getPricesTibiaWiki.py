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
MELEE_ONE_HANDED = []
MELEE_TWO_HANDED = []
OUTPUT_FILE = "getItemsEPrecosTibia\\assets\\output.txt"
OUTPUT_ITENS_COMPRAVEIS = "getItemsEPrecosTibia\\assets\\output_compraveis.txt"
OUTPUT_ITENS_VENDIVEIS = "getItemsEPrecosTibia\\assets\\output_vendiveis.txt"
INPUT_ITENS_COMPRAVEIS_FIXOS = "getItemsEPrecosTibia\\assets\\_compraveis_fixos.txt"
INPUT_ITENS_VENDIVEIS_FIXOS = "getItemsEPrecosTibia\\assets\\_vendiveis_fixos.txt"
XML_FILE = "getItemsEPrecosTibia\\assets\\items.xml"

def main():

    # ex.getInfosFromItensWiki(ITEMS_WIKI)
    am.getInfosFromItensWiki(ITEMS_WIKI)
    it.getInfosFromItensWiki(ITEMS_WIKI)
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
        f.write(f"{len(ITEMS_WIKI)} itens.\n")
        for item in ITEMS_WIKI:
            if (item_type is None) or item_type != item.type:
                item_type = item.type
                f.write(f"-----------------Slot: " + item.type + "-----------------\n")
            f.write(item.__repr__())
        print("Finalizada escrita de itens gerais.")


    with open(OUTPUT_ITENS_COMPRAVEIS, "w", encoding="utf-8") as f:
        f.write(f"{len(ITEMS_COMPRAVEIS)} itens compráveis.\n")
        for item in ITEMS_COMPRAVEIS:
            f.write(item)
        with open(INPUT_ITENS_COMPRAVEIS_FIXOS, "r", encoding="utf-8") as fcf:
            for line in fcf.readlines():
                f.write(line)
        print("Finalizada escrita de itens compráveis.")

    with open(OUTPUT_ITENS_VENDIVEIS, "w", encoding="utf-8") as f:
        f.write(f"{len(ITEMS_VENDIVEIS)} itens vendíveis.\n")
        for item in ITEMS_VENDIVEIS:
            f.write(item)
        with open(INPUT_ITENS_VENDIVEIS_FIXOS, "r", encoding="utf-8") as fvf:
            for line in fvf.readlines():
                f.write(line)
        print("Finalizada escrita de itens vendíveis.")
    
if __name__ == "__main__":
    main()
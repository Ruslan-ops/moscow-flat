import json
import os
import re
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
CIAN_PATH = f"{ROOT}/data/cian/offers.json"
DB_PATH = f"{ROOT}/data/avito/collector.sqlite"
OUT_PATH = f"{ROOT}/data/report/avito_matches.json"
STREET_TYPES = {"проспект", "улица", "переулок", "шоссе", "набережная", "бульвар", "площадь", "проезд", "тупик", "аллея", "просп", "пер", "наб"}
AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*м[²2]")
FLOOR_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*эт")


def norm_house(text):
    s = text.lower().replace("ё", "е")
    s = re.sub(r"корпус|корп", "к", s)
    s = re.sub(r"строение|стр", "с", s)
    s = re.sub(r"[\s.]", "", s)
    s = re.sub(r"^дом", "", s)
    return s if s[:1].isdigit() else None


def norm_street(text):
    s = text.lower().replace("ё", "е").replace("пр-кт", "проспект").replace("пр-т", "проспект").replace("пр-д", "проезд").replace("б-р", "бульвар")
    s = re.sub(r"[^\w\s]", " ", s)
    return {t for t in s.split() if len(t) > 2 and t not in STREET_TYPES}


def parse_offer(offer):
    parts = [p.strip() for p in offer["geo"]["address"].split(",")]
    return {"house": norm_house(parts[-1]), "street": norm_street(parts[-2]), "area": float(offer["totalArea"]), "floor": offer["floorNumber"], "floors": offer["building"]["floorsCount"]}


def parse_card(card):
    title = card["title"]
    address_parts = card["address"].split(",")
    area = AREA_RE.search(title)
    floor = FLOOR_RE.search(title)
    house_tokens = address_parts[1].split() if len(address_parts) > 1 else []
    return {"url": card["url"], "price": card["price"], "house": norm_house(house_tokens[0]) if house_tokens else None, "street": norm_street(address_parts[0]), "area": float(area.group(1).replace(",", ".")) if area else None, "floor": int(floor.group(1)) if floor else None, "floors": int(floor.group(2)) if floor else None}


def load_cards():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT json FROM search_cards").fetchall()
    conn.close()
    return [parse_card(json.loads(r[0])) for r in rows]


def match(cian_offer, avito_cards):
    c = parse_offer(cian_offer)
    hits = [a for a in avito_cards if c["house"] and a["house"] == c["house"] and a["street"] & c["street"] and a["area"] is not None and abs(a["area"] - c["area"]) <= 1.5 and (a["floor"] is None or a["floor"] == c["floor"]) and (a["floors"] is None or a["floors"] == c["floors"])]
    if not hits:
        return None
    best = min(hits, key=lambda a: abs(a["area"] - c["area"]))
    return {"url": best["url"], "price": best["price"], "score": 1}


def main():
    ids = json.loads(sys.argv[1])
    with open(CIAN_PATH, encoding="utf-8") as f:
        offers = {o["cianId"]: o for o in json.load(f)}
    cards = load_cards()
    result = {i: match(offers[i], cards) if i in offers else None for i in ids}
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"matched {sum(1 for v in result.values() if v)} of {len(result)}")


if __name__ == "__main__":
    main()

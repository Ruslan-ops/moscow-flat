import json
import sys
from collections import Counter
sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 1)[0])
from layers import ROOT
from score import listing_score, load_layers

with open(f"{ROOT}/data/cian/offers.json", encoding="utf-8") as f:
    offers = json.load(f)
layers = load_layers()
rejects = Counter()
ranked = []
for o in offers:
    s = listing_score(o, layers)
    if s["rejected"]:
        rejects[s["reason"]] += 1
        continue
    b = o.get("building") or {}
    ranked.append({"cianId": o.get("cianId"), "fullUrl": o.get("fullUrl"), "price": o["bargainTerms"]["price"], "totalArea": o.get("totalArea"), "floorNumber": o.get("floorNumber"), "floorsCount": b.get("floorsCount"), "materialType": b.get("materialType"), "buildYear": b.get("buildYear"), "address": o["geo"].get("address"), **s})
ranked.sort(key=lambda r: -r["total"])
with open(f"{ROOT}/data/ranked/cian_ranked.json", "w", encoding="utf-8") as f:
    json.dump(ranked, f, ensure_ascii=False, indent=1)
print("offers", len(offers), "ranked", len(ranked), dict(rejects))
for r in ranked[:15]:
    print(r["cianId"], r["price"], r["totalArea"], f"{r['floorNumber']}/{r['floorsCount']}", r["materialType"], r["buildYear"], r["metro"], r["metro_walk"], round(r["total"], 3), r["tier"])

import json

ROOT = "D:/Users/Ruslan/VsCodeProjects/moscow-flat"
ranked = {x["cianId"]: x for x in json.load(open(f"{ROOT}/data/ranked/cian_ranked.json", encoding="utf-8"))}
offers = {o["cianId"]: o for o in json.load(open(f"{ROOT}/data/cian/offers.json", encoding="utf-8"))}
reviews = {r["cianId"]: r for r in json.load(open(f"{ROOT}/data/reviews/all_sonnet.json", encoding="utf-8"))}
reviews.update({r["cianId"]: r for r in json.load(open(f"{ROOT}/data/reviews/align_opus.json", encoding="utf-8"))})
out = []
for cid, rv in reviews.items():
    if rv["pred"] < 3.5 or cid not in ranked or cid not in offers:
        continue
    r = ranked[cid]
    o = offers[cid]
    out.append({
        "cianId": cid, "url": o["fullUrl"].split("?")[0], "price": r["price"], "totalArea": float(r["totalArea"]),
        "kitchen": float(o["kitchenArea"]) if o.get("kitchenArea") else None, "rooms": o.get("roomsCount"),
        "floorNumber": r["floorNumber"], "floorsCount": r["floorsCount"], "materialType": r["materialType"], "buildYear": r["buildYear"],
        "metro": r["metro"], "metro_walk": r["metro_walk"], "address": r["address"], "lat": o["geo"]["coordinates"]["lat"], "lng": o["geo"]["coordinates"]["lng"],
        "move_in_cost": r["move_in_cost"], "deposit": o["bargainTerms"].get("deposit") or 0, "owner": bool(o.get("isByHomeowner")), "tier": r["tier"], "total": r["total"],
        "review": {k: rv.get(k) for k in ("base", "soft", "pred", "verdict", "summary", "fixable", "red_flags")},
        "place": {"park_walk": r["park_walk"], "culture25": r["culture25"], "job_p50": r["job_p50"], "quiet": r["components"]["quiet"]},
        "avito_url": None,
    })
out.sort(key=lambda f: (-f["review"]["pred"], -f["total"]))
for i, f in enumerate(out, 1):
    f["rank"] = i
json.dump(out, open(f"{ROOT}/data/report/finalists.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(out))

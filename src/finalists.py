import json

ROOT = "D:/Users/Ruslan/VsCodeProjects/moscow-flat"
OVERRIDES = {335289519: 3.5, 336160927: 3.5, 335106581: 3.5, 332162331: 3.5, 336068604: 3.5, 335502057: 3.5, 330098588: 3.0, 335316719: 3.5, 269077216: 4.5, 295837800: 3.5, 203784893: 3.5}
EXCLUDE = {335531859}
MAX_FINALISTS = 30


def verdict(pred):
    return "смотреть" if pred >= 4 else "запасной" if pred >= 3.5 else "под вопросом" if pred >= 3 else "нет"


ranked = {x["cianId"]: x for x in json.load(open(f"{ROOT}/data/ranked/cian_ranked.json", encoding="utf-8"))}
offers = {o["cianId"]: o for o in json.load(open(f"{ROOT}/data/cian/offers.json", encoding="utf-8"))}
reviews = {r["cianId"]: r for r in json.load(open(f"{ROOT}/data/reviews/all_sonnet.json", encoding="utf-8"))}
reviews.update({r["cianId"]: r for r in json.load(open(f"{ROOT}/data/reviews/align_opus.json", encoding="utf-8"))})
avito = json.load(open(f"{ROOT}/data/report/avito_matches.json", encoding="utf-8"))
out = []
for cid, rv in reviews.items():
    pred = OVERRIDES.get(cid, rv["pred"])
    r = ranked.get(cid)
    if pred < 3.5 or cid in EXCLUDE or r is None or r.get("rejected") or cid not in offers:
        continue
    o = offers[cid]
    match = avito.get(str(cid))
    out.append({
        "cianId": cid, "url": o["fullUrl"].split("?")[0], "price": r["price"], "totalArea": float(r["totalArea"]),
        "kitchen": float(o["kitchenArea"]) if o.get("kitchenArea") else None, "rooms": o.get("roomsCount"),
        "floorNumber": r["floorNumber"], "floorsCount": r["floorsCount"], "materialType": r["materialType"], "buildYear": r["buildYear"],
        "metro": r["metro"], "metro_walk": r["metro_walk"], "address": r["address"], "lat": o["geo"]["coordinates"]["lat"], "lng": o["geo"]["coordinates"]["lng"],
        "move_in_cost": r["move_in_cost"], "deposit": o["bargainTerms"].get("deposit") or 0, "owner": bool(o.get("isByHomeowner")), "tier": r["tier"], "total": r["total"],
        "review": {**{k: rv.get(k) for k in ("base", "soft", "summary", "fixable", "red_flags")}, "pred": pred, "verdict": verdict(pred)},
        "place": {"park_walk": r["park_walk"], "culture25": r["culture25"], "job_p50": r["job_p50"], "quiet": r["components"]["quiet"]},
        "avito_url": match["url"] if match else None,
        "final": 0.5 * r["total"] + 0.5 * (pred - 1) / 4,
    })
out.sort(key=lambda f: -f["final"])
top = out[:MAX_FINALISTS]
top += [f for f in out[MAX_FINALISTS:] if f["tier"] == "A" and f["review"]["pred"] >= 4]
for i, f in enumerate(top, 1):
    f["rank"] = i
json.dump(top, open(f"{ROOT}/data/report/finalists.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump([f["cianId"] for f in top], open(f"{ROOT}/data/report/finalist_ids.json", "w"))
print(len(out), len(top), sum(f["tier"] == "A" for f in top), sum(f["review"]["pred"] >= 4 for f in top))

import json
import sys
import numpy as np
from collections import Counter
sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 1)[0])
from layers import ROOT
from score import listing_score, load_layers, haversine_m, num

with open(f"{ROOT}/data/cian/offers.json", encoding="utf-8") as f:
    offers = json.load(f)
layers = load_layers()


def bucket(o):
    return 2 if (o.get("roomsCount") or 1) >= 2 else 1


def price_ratios(offers):
    ok = [k for k, o in enumerate(offers) if num((o.get("bargainTerms") or {}).get("price")) and num(o.get("totalArea")) and (o.get("geo") or {}).get("coordinates")]
    lat = np.array([offers[k]["geo"]["coordinates"]["lat"] for k in ok])
    lng = np.array([offers[k]["geo"]["coordinates"]["lng"] for k in ok])
    ppm = np.array([num(offers[k]["bargainTerms"]["price"]) / num(offers[k]["totalArea"]) for k in ok])
    bk = np.array([bucket(offers[k]) for k in ok])
    ratios = {}
    for n, k in enumerate(ok):
        d = haversine_m(lat[n], lng[n], lat, lng)
        d[n] = np.inf
        d[bk != bk[n]] = np.inf
        for radius in (3000, 6000):
            idx = np.argsort(d)[:30]
            idx = idx[d[idx] <= radius]
            if len(idx) >= 10:
                ratios[k] = ppm[n] / np.median(ppm[idx])
                break
    return ratios


def dedupe(ranked):
    order = sorted(range(len(ranked)), key=lambda k: ("owner" not in ranked[k]["flags"], ranked[k]["price"]))
    taken = set()
    for k in order:
        if k in taken:
            continue
        r = ranked[k]
        r["duplicates"] = []
        for m in order:
            c = ranked[m]
            if m == k or m in taken or c["floorNumber"] != r["floorNumber"] or abs(float(c["totalArea"]) - float(r["totalArea"])) > 1.5 or haversine_m(r["lat"], r["lng"], c["lat"], c["lng"]) > 25:
                continue
            taken.add(m)
            c["duplicate_of"] = r["cianId"]
            r["duplicates"].append({"cianId": c["cianId"], "fullUrl": c["fullUrl"]})
        taken.add(k)


def shortlist(ranked):
    out = []
    per_metro = Counter()
    for r in ranked:
        if r["soft_reject"] or r.get("duplicate_of") or per_metro[r["metro"]] >= 8:
            continue
        per_metro[r["metro"]] += 1
        out.append(r)
    return out[:80]


ratios = price_ratios(offers)
rejects = Counter()
ranked = []
for k, o in enumerate(offers):
    s = listing_score(o, layers, ratios.get(k))
    if s["rejected"]:
        rejects[s["reason"]] += 1
        continue
    b = o.get("building") or {}
    ranked.append({"cianId": o.get("cianId"), "fullUrl": o.get("fullUrl"), "price": o["bargainTerms"]["price"], "totalArea": o.get("totalArea"), "floorNumber": o.get("floorNumber"), "floorsCount": b.get("floorsCount"), "materialType": b.get("materialType"), "buildYear": b.get("buildYear"), "address": o["geo"].get("address"), "okrug": next((d["name"] for d in o["geo"].get("districts") or [] if d.get("type") == "okrug"), None), "lat": o["geo"]["coordinates"]["lat"], "lng": o["geo"]["coordinates"]["lng"], **s})
ranked.sort(key=lambda r: (r["soft_reject"] is not None, -r["total"]))
dedupe(ranked)
top = shortlist(ranked)
with open(f"{ROOT}/data/ranked/cian_ranked.json", "w", encoding="utf-8") as f:
    json.dump(ranked, f, ensure_ascii=False, indent=1)
with open(f"{ROOT}/data/ranked/shortlist_candidates.json", "w", encoding="utf-8") as f:
    json.dump(top, f, ensure_ascii=False, indent=1)
flag_counts = Counter(fl for r in ranked for fl in r["flags"])
print("offers", len(offers), "ranked", len(ranked), "hard_rejects", dict(rejects))
print("soft_rejects", dict(Counter(r["soft_reject"] for r in ranked if r["soft_reject"])), "duplicates", sum(1 for r in ranked if r.get("duplicate_of")))
print("flags", dict(flag_counts))
print("tags", dict(Counter(t for r in ranked for t in r["tags"])))
print("top tiers", dict(Counter(r["tier"] for r in top)), "okrug", dict(Counter(r["okrug"] for r in top)))
print("metro", dict(Counter(r["metro"] for r in top)))
for r in top[:15]:
    print(r["cianId"], r["price"], r["totalArea"], f"{r['floorNumber']}/{r['floorsCount']}", r["materialType"], r["buildYear"], r["metro"], r["metro_walk"], round(r["total"], 3), r["tier"], round(r["price_ratio"] or 0, 2), r["flags"], r["tags"])

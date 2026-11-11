import json
import math
import time
import requests

BBOX = "55.55,37.35,55.92,37.86"
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
NAME_RE = "дизайн|design|визуал|render|3d|архитект"
QUERIES = [
    ("florist", f'nwr["shop"="florist"]({BBOX});'),
    ("archviz", f'nwr["office"="architect"]({BBOX});'),
    ("design", f'nwr["office"="company"]["name"~"{NAME_RE}",i]({BBOX});'),
    ("decor", f'nwr["office"="event_management"]({BBOX});nwr["shop"="party"]({BBOX});nwr["amenity"="events_venue"]({BBOX});nwr["office"="advertising_agency"]({BBOX});'),
]
HEADERS = {"User-Agent": "flat-research/1.0"}


def fetch(body):
    for attempt in range(6):
        url = ENDPOINTS[attempt % 2]
        r = requests.post(url, data={"data": f"[out:json][timeout:90];({body});out center tags;"}, headers=HEADERS, timeout=120)
        print(url, r.status_code)
        if r.status_code == 200:
            return r.json()["elements"]
        time.sleep(10 * (attempt + 1))
    raise RuntimeError("overpass failed")


def dist(lat, lng):
    return math.hypot((lat - 55.7558) * 111.2, (lng - 37.6176) * 111.2 * math.cos(math.radians(55.75)))


out = []
seen = set()
for category, body in QUERIES:
    for e in fetch(body):
        lat = e.get("lat") or e["center"]["lat"]
        lng = e.get("lon") or e["center"]["lon"]
        key = (e["type"], e["id"])
        if key in seen:
            continue
        seen.add(key)
        tags = e["tags"]
        cat = "florist" if category == "florist" else category
        item = {"name": tags.get("name", ""), "category": cat, "lat": round(lat, 5), "lng": round(lng, 5)}
        if category == "florist" and tags.get("wholesale") == "yes":
            item["wholesale"] = True
        out.append(item)
    time.sleep(3)

with open("data/jobs/job_points.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

for c in ["florist", "archviz", "decor", "design"]:
    pts = [p for p in out if p["category"] == c]
    d = [dist(p["lat"], p["lng"]) for p in pts]
    n = max(len(d), 1)
    print(c, len(pts), round(100 * sum(x < 2.2 for x in d) / n), round(100 * sum(2.2 <= x < 5 for x in d) / n), round(100 * sum(x >= 5 for x in d) / n))

with open("data/jobs/creative_hubs.json", encoding="utf-8") as f:
    hubs = json.load(f)
hubs = [h for h in hubs if h["name"] not in ("Москва-Сити", "Арма")]
hubs.append({"name": "Москва-Сити", "type": "archviz", "lat": 55.749, "lng": 37.537, "weight": 0.6})
hubs.append({"name": "Арма", "type": "decor", "lat": 55.7585, "lng": 37.664, "weight": 0.7})
with open("data/jobs/creative_hubs.json", "w", encoding="utf-8") as f:
    json.dump(hubs, f, ensure_ascii=False, indent=1)
print(len(out), len(hubs))

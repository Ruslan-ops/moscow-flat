import json
import sys
import time
import numpy as np

sys.path.insert(0, "d:/Users/Ruslan/VsCodeProjects/moscow-flat/src")
import dgis_cache

ENV = "d:/Users/Ruslan/VsCodeProjects/moscow-flat/.env"
COUNT_PATH = "data/jobs/dgis_request_count.json"
OUT_PATH = "data/jobs/dgis_orgs.json"
OSM_PATH = "data/jobs/job_points.json"
C_LAT = 55.7558
C_LON = 37.6176
KM_LAT = 111.19
KM_LON = 111.19 * np.cos(np.radians(C_LAT))
STEP_KM = 8.5
TILE_RADIUS = 6200
MAX_CALLS = 130
RUN = {"calls": 0}
FIELDS = "items.point,items.rubrics,items.org,items.address_name"
RUBRIC_GROUPS = {"decor": "9220,630", "archviz": "273,331"}
TEXT_QUERIES = ["флористическая студия", "цветочная база", "оптовая продажа цветов"]


def key():
    for line in open(ENV, encoding="utf-8"):
        if line.startswith("DGIS_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")


def counts():
    try:
        return json.load(open(COUNT_PATH))
    except FileNotFoundError:
        return {"places": 0, "routing": 0}


def places(params):
    if RUN["calls"] >= MAX_CALLS:
        raise SystemExit("run cap reached")
    data, real = dgis_cache.cached("GET", "https://catalog.api.2gis.com/3.0/items", params=params, key=key())
    if real:
        RUN["calls"] += 1
        c = counts()
        c["places"] += 1
        json.dump(c, open(COUNT_PATH, "w"))
        time.sleep(0.3)
    if data["meta"]["code"] in (403, 429):
        raise SystemExit(f"limit error {data['meta']['code']}")
    return data


def fetch_all(params):
    items = []
    total = None
    for page in range(1, 6):
        j = places({**params, "type": "branch", "page_size": 10, "page": page, "fields": FIELDS})
        if j["meta"]["code"] != 200:
            break
        total = j["result"]["total"]
        got = j["result"]["items"]
        items += got
        if len(items) >= total or len(got) < 10:
            break
    return items, total


def tiles():
    h = np.arange(-1, 2) * STEP_KM
    return [(C_LAT + y / KM_LAT, C_LON + x / KM_LON) for y in h for x in h]


def collect(found, stats):
    for cat, rubrics in RUBRIC_GROUPS.items():
        for lat, lon in tiles():
            items, total = fetch_all({"rubric_id": rubrics, "point": f"{lon:.5f},{lat:.5f}", "radius": TILE_RADIUS})
            stats.append([cat, round(lat, 4), round(lon, 4), total, len(items)])
            for it in items:
                found.setdefault(it["id"], (cat, it))
        print(cat, len(found), counts())
    for q in TEXT_QUERIES:
        items, total = fetch_all({"q": q, "point": f"{C_LON},{C_LAT}", "radius": 17000})
        stats.append(["florist_studio", q, total, len(items)])
        for it in items:
            found.setdefault(it["id"], ("florist_studio", it))
        print(q, len(found), counts())


def convert(found):
    out = []
    for bid, (cat, it) in found.items():
        if "point" not in it:
            continue
        rubs = [r["name"] for r in it.get("rubrics", [])]
        out.append({"id": bid, "name": it.get("name", ""), "category": cat, "rubric": rubs, "retail_flowers": "Цветы" in rubs and cat == "florist_studio", "lat": it["point"]["lat"], "lng": it["point"]["lon"], "address": it.get("address_name", "")})
    return out


def analyse(out):
    for cat in sorted({o["category"] for o in out}):
        sub = [o for o in out if o["category"] == cat]
        d = np.hypot((np.array([o["lat"] for o in sub]) - C_LAT) * KM_LAT, (np.array([o["lng"] for o in sub]) - C_LON) * KM_LON)
        print(cat, len(sub), f"<2.2km {np.mean(d < 2.2):.0%} 2.2-5km {np.mean((d >= 2.2) & (d < 5)):.0%} >5km {np.mean(d >= 5):.0%}")


def grid(points, edges_lat, edges_lon):
    a = np.array(points)
    return np.histogram2d(a[:, 0], a[:, 1], bins=[edges_lat, edges_lon])[0].ravel()


def correlate(out):
    osm = json.load(open(OSM_PATH, encoding="utf-8"))
    el = C_LAT + np.arange(-17, 17.01, 2) / KM_LAT
    eo = C_LON + np.arange(-17, 17.01, 2) / KM_LON
    for cat_d, cat_o in [("decor", ["decor"]), ("archviz", ["archviz"]), ("florist_studio", ["florist"])]:
        d = grid([[o["lat"], o["lng"]] for o in out if o["category"] == cat_d], el, eo)
        o = grid([[p["lat"], p["lng"]] for p in osm if p["category"] in cat_o], el, eo)
        print("corr", cat_d, len(d), float(np.corrcoef(d, o)[0, 1]), float(np.corrcoef(np.log1p(d), np.log1p(o))[0, 1]))


if __name__ == "__main__":
    if sys.argv[1:] == ["analyse"]:
        out = json.load(open(OUT_PATH, encoding="utf-8"))
    else:
        found, stats = {}, []
        try:
            collect(found, stats)
        except SystemExit as e:
            print("stopped", e)
        out = convert(found)
        json.dump(out, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False)
        json.dump(stats, open("data/jobs/dgis_tile_stats.json", "w", encoding="utf-8"), ensure_ascii=False)
    analyse(out)
    correlate(out)

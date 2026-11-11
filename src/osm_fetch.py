import json
import math
import re
import sys
import time
import requests
from shapely.geometry import Polygon, LineString, box, mapping
from shapely.ops import linemerge, polygonize, unary_union, transform

BBOX = (55.55, 37.35, 55.92, 37.86)
BBOX_STR = f"{BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]}"
ENDPOINTS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
HEADERS = {"User-Agent": "moscow-flat-research/1.0 (personal flat search)"}
OUT = "d:/Users/Ruslan/VsCodeProjects/moscow-flat/data/osm"
COS = math.cos(math.radians(55.75))
BOX = box(BBOX[1], BBOX[0], BBOX[3], BBOX[2])


def to_m(x, y, z=None):
    return x * COS * 111320.0, y * 110570.0


def to_deg(x, y, z=None):
    return x / (COS * 111320.0), y / 110570.0


def fetch(body):
    q = f"[out:json][timeout:180];{body}"
    for attempt in range(3):
        for url in ENDPOINTS:
            try:
                r = requests.post(url, data={"data": q}, headers=HEADERS, timeout=240)
                if r.status_code == 200:
                    time.sleep(5)
                    return r.json()["elements"]
                print(url, r.status_code)
            except Exception as e:
                print(url, repr(e))
            time.sleep(10)
    return None


def save(name, data):
    with open(f"{OUT}/{name}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def way_line(geom):
    return LineString([(p["lon"], p["lat"]) for p in geom])


def rings_union(lines):
    merged = linemerge(unary_union(lines))
    return unary_union(list(polygonize(merged)))


def element_polygon(el):
    if el["type"] == "way":
        pts = el.get("geometry", [])
        if len(pts) < 4 or pts[0] != pts[-1]:
            return None
        return Polygon([(p["lon"], p["lat"]) for p in pts]).buffer(0)
    outers, inners = [], []
    for m in el.get("members", []):
        if m["type"] != "way" or not m.get("geometry") or len(m["geometry"]) < 2:
            continue
        (inners if m["role"] == "inner" else outers).append(way_line(m["geometry"]))
    if not outers:
        return None
    poly = rings_union(outers)
    if inners and not poly.is_empty:
        poly = poly.difference(rings_union(inners))
    return poly


def fetch_green():
    body = f"""(
nwr["leisure"~"^(park|garden)$"]({BBOX_STR});
nwr["landuse"="forest"]({BBOX_STR});
nwr["natural"="wood"]({BBOX_STR});
nwr["boundary"="protected_area"]({BBOX_STR});
);out geom;"""
    els = fetch(body)
    feats = []
    for el in els:
        tags = el.get("tags", {})
        if el["type"] == "node":
            continue
        if tags.get("leisure") == "garden" and tags.get("garden:type") in ("private", "residential"):
            continue
        poly = element_polygon(el)
        if poly is None or poly.is_empty:
            continue
        poly = poly.intersection(BOX)
        if poly.is_empty:
            continue
        pm = transform(to_m, poly)
        area_ha = pm.area / 10000.0
        if area_ha < 2:
            continue
        simp = transform(to_deg, pm.simplify(15, preserve_topology=True))
        if simp.is_empty:
            continue
        kind = tags.get("leisure") or tags.get("landuse") or tags.get("natural") or tags.get("boundary")
        feats.append({"type": "Feature", "properties": {"name": tags.get("name"), "kind": kind, "area_ha": round(area_ha, 2)}, "geometry": mapping(simp)})
    save("green", {"type": "FeatureCollection", "features": feats})
    print("green", len(feats), "total_ha", round(sum(f["properties"]["area_ha"] for f in feats)))
    for key in ["Сокольники", "Измайловский", "Нескучный", "Горького", "Лосиный"]:
        hits = [(f["properties"]["name"], f["properties"]["area_ha"]) for f in feats if f["properties"]["name"] and key in f["properties"]["name"]]
        print(key, hits[:6])


def fetch_culture():
    body = f"""(
nwr["tourism"~"^(museum|gallery)$"]({BBOX_STR});
nwr["amenity"~"^(arts_centre|exhibition_centre)$"]({BBOX_STR});
);out center tags;"""
    els = fetch(body)
    rows = []
    for el in els:
        tags = el.get("tags", {})
        c = el if el["type"] == "node" else el.get("center")
        if not c:
            continue
        rows.append({"name": tags.get("name"), "kind": tags.get("tourism") or tags.get("amenity"), "lat": c["lat"], "lng": c["lon"]})
    save("culture", rows)
    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    print("culture", len(rows), kinds)


def fetch_noise():
    body = f"""(
way["highway"~"^(motorway|trunk|primary)$"]({BBOX_STR});
way["railway"="rail"][!"abandoned"][!"disused"][!"service"]({BBOX_STR});
way["railway"="tram"]({BBOX_STR});
);out geom tags;"""
    els = fetch(body)
    feats = []
    for el in els:
        tags = el.get("tags", {})
        if len(el.get("geometry", [])) < 2:
            continue
        if tags.get("highway"):
            cls = tags["highway"]
        elif tags.get("railway") == "tram":
            cls = "tram"
        else:
            cls = "rail"
        simp = transform(to_deg, transform(to_m, way_line(el["geometry"])).simplify(10, preserve_topology=True))
        feats.append({"type": "Feature", "properties": {"class": cls, "name": tags.get("name")}, "geometry": mapping(simp)})
    save("noise", {"type": "FeatureCollection", "features": feats})
    counts = {}
    for f in feats:
        counts[f["properties"]["class"]] = counts.get(f["properties"]["class"], 0) + 1
    print("noise", len(feats), counts)


def parse_year(s):
    m = re.search(r"(1[5-9]\d\d|20\d\d)", s or "")
    return int(m.group(1)) if m else None


def parse_levels(s):
    m = re.match(r"\s*(\d+)", s or "")
    return int(m.group(1)) if m else None


def building_tiles(n):
    s, w, nn, e = BBOX
    for i in range(n):
        for j in range(n):
            yield (s + (nn - s) * i / n, w + (e - w) * j / n, s + (nn - s) * (i + 1) / n, w + (e - w) * (j + 1) / n)


def fetch_buildings():
    seen = {}
    for t in building_tiles(4):
        bb = f"{t[0]:.5f},{t[1]:.5f},{t[2]:.5f},{t[3]:.5f}"
        body = f'(way["building"]["start_date"]({bb});way["building"]["building:year"]({bb});way["building"]["building:levels"]({bb}););out center tags;'
        els = fetch(body)
        if els is None:
            print("tile failed", bb)
            continue
        for el in els:
            if el.get("center"):
                seen[el["id"]] = el
        print("tile", bb, len(els), len(seen))
        sys.stdout.flush()
    rows = []
    for el in seen.values():
        tags = el["tags"]
        rows.append({"lat": el["center"]["lat"], "lng": el["center"]["lon"], "year": parse_year(tags.get("start_date") or tags.get("building:year")), "levels": parse_levels(tags.get("building:levels")), "material": tags.get("building:material"), "name": tags.get("name")})
    save("buildings_era", rows)
    print("buildings", len(rows), "with_year", sum(1 for r in rows if r["year"]), "with_levels", sum(1 for r in rows if r["levels"]), "with_material", sum(1 for r in rows if r["material"]))


if __name__ == "__main__":
    layers = sys.argv[1:] or ["green", "culture", "noise", "buildings"]
    for layer in layers:
        {"green": fetch_green, "culture": fetch_culture, "noise": fetch_noise, "buildings": fetch_buildings}[layer]()

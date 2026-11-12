import json
import sys
sys.path.insert(0, "D:/Users/Ruslan/VsCodeProjects/moscow-flat/src")
from osm_fetch import fetch, save, BBOX_STR


def points(els, kind):
    out = []
    for e in els:
        c = e.get("center") or e
        if "lat" in c:
            out.append({"kind": kind, "lat": round(c["lat"], 6), "lng": round(c["lon"], 6), "name": (e.get("tags") or {}).get("name")})
    return out


construction = fetch(f'(way["landuse"="construction"]({BBOX_STR});way["building"="construction"]({BBOX_STR});relation["landuse"="construction"]({BBOX_STR}););out center tags;')
night = fetch(f'(node["amenity"~"^(bar|pub|nightclub)$"]({BBOX_STR});way["amenity"~"^(bar|pub|nightclub)$"]({BBOX_STR}););out center tags;')
fire = fetch(f'(node["amenity"="fire_station"]({BBOX_STR});way["amenity"="fire_station"]({BBOX_STR}););out center tags;')
save("extra", points(construction, "construction") + points(night, "night") + points(fire, "fire"))
print(len(construction), len(night), len(fire))

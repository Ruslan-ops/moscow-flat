import sys
import json
import numpy as np
import shapely
from shapely.geometry import shape
from shapely import STRtree
sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 1)[0])
from transit import LAT0, LON0, DLAT, DLON, KM_LAT, KM_LON, WALK_KMH, door_to_door

ROOT = __file__.replace("\\", "/").rsplit("/src/", 1)[0]
LAYERS_DIR = f"{ROOT}/data/layers"
ORG_WEIGHTS = {"decor": 1.0, "archviz": 0.9, "florist_studio": 0.8}
HUB_FACTOR = 25
OSM_JOB_WEIGHT = 0.3
PARK_DETOUR = 1.25
_trees = {}


def read_json(path):
    with open(f"{ROOT}/{path}", encoding="utf-8") as f:
        return json.load(f)


def grid_axes():
    base = read_json("data/metro/grid_walk_to_metro.json")
    return base["nlat"], base["nlon"], LAT0 + (np.arange(base["nlat"]) + 0.5) * DLAT, LON0 + (np.arange(base["nlon"]) + 0.5) * DLON


def save_grid(name, values):
    nlat, nlon = values.shape
    with open(f"{LAYERS_DIR}/{name}.json", "w", encoding="utf-8") as f:
        json.dump({"lat0": LAT0, "lon0": LON0, "dlat": DLAT, "dlon": DLON, "nlat": nlat, "nlon": nlon, "values": np.round(values, 2).tolist()}, f)


def project_m(latlon):
    a = np.asarray(latlon, dtype=float).reshape(-1, 2)
    return np.column_stack([a[:, 1] * KM_LON * 1000, a[:, 0] * KM_LAT * 1000])


def project_geom(geom):
    return shapely.transform(geom, lambda c: c * np.array([KM_LON * 1000, KM_LAT * 1000]))


def nearest_dist_m(key, geoms, latlon):
    if key not in _trees:
        _trees[key] = (STRtree(geoms), geoms)
    tree = _trees[key][0]
    pts = shapely.points(project_m(latlon))
    return tree.query_nearest(pts, return_distance=True, all_matches=False)[1]


def line_geoms(classes):
    feats = read_json("data/osm/noise.json")["features"]
    return [project_geom(shape(f["geometry"])) for f in feats if f["properties"]["class"] in classes]


def noise_distances(latlon):
    return {
        "noise_dist": nearest_dist_m("noise", line_geoms({"motorway", "trunk"}), latlon),
        "rail_dist": nearest_dist_m("rail", line_geoms({"rail"}), latlon),
        "primary_dist": nearest_dist_m("primary", line_geoms({"primary"}), latlon),
    }


def park_walk(latlon, min_ha):
    feats = read_json("data/osm/green.json")["features"]
    geoms = [project_geom(shape(f["geometry"])) for f in feats if f["properties"]["area_ha"] >= min_ha]
    return nearest_dist_m(f"park{min_ha}", geoms, latlon) / 1000 * PARK_DETOUR / WALK_KMH * 60


def job_destinations():
    pts = []
    weights = []
    for o in read_json("data/jobs/dgis_orgs.json"):
        pts.append([o["lat"], o["lng"]])
        weights.append(ORG_WEIGHTS[o["category"]])
    for h in read_json("data/jobs/creative_hubs.json"):
        pts.append([h["lat"], h["lng"]])
        weights.append(h["weight"] * HUB_FACTOR)
    for p in read_json("data/jobs/job_points.json"):
        if p["category"] in ("decor", "archviz"):
            pts.append([p["lat"], p["lng"]])
            weights.append(OSM_JOB_WEIGHT)
    return np.array(pts), np.array(weights)


def job_layers(cells):
    pts, w = job_destinations()
    t = door_to_door(cells, pts)
    order = np.argsort(t, axis=1)
    cum = np.cumsum(w[order], axis=1)
    median_idx = (cum >= cum[:, -1:] / 2).argmax(axis=1)
    p50 = np.take_along_axis(t, order, axis=1)[np.arange(len(t)), median_idx]
    return (t <= 30) @ w / w.sum(), (t <= 40) @ w / w.sum(), p50


def main():
    nlat, nlon, lats, lons = grid_axes()
    cells = np.array([[a, b] for a in lats for b in lons])
    shape2 = (nlat, nlon)
    layers = {"walk_metro": np.array(read_json("data/metro/grid_walk_to_metro.json")["values"])}
    layers["job_share30"], layers["job_share40"], layers["job_p50"] = [x.reshape(shape2) for x in job_layers(cells)]
    layers["park_walk"] = park_walk(cells, 10).reshape(shape2)
    layers["park_walk_small"] = park_walk(cells, 2).reshape(shape2)
    culture = np.array([[c["lat"], c["lng"]] for c in read_json("data/osm/culture.json")])
    layers["culture25"] = (door_to_door(cells, culture) <= 25).sum(axis=1).reshape(shape2)
    for k, v in noise_distances(cells).items():
        layers[k] = v.reshape(shape2)
    for k, v in layers.items():
        save_grid(k, v)
    np.savez_compressed(f"{LAYERS_DIR}/all.npz", **layers)
    for k, v in layers.items():
        print(k, float(v.min()), float(np.median(v)), float(v.max()))


if __name__ == "__main__":
    main()

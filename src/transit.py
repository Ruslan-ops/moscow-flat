import json
import os
import time
import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

LAT0 = 55.55
LON0 = 37.35
DLAT = 0.0025
DLON = 0.004
LAT1 = 55.92
LON1 = 37.86
KM_LAT = 111.19
KM_LON = 111.19 * np.cos(np.radians(55.75))
SPEED = 40.0
DWELL = 0.6
BOARD_WAIT = 3.0
WALK_KMH = 4.8
WALK_DETOUR = 1.3
RING_LINES = {"5", "95", "97"}
RING_MAX_KM = 3.0
TRANSFER_MAX_KM = 0.4
TRANSFER_BASE = 4.5
TRANSFER_FREE_KM = 0.15
ACCESS_K = 4
ACCESS_MAX_KM = 2.0
META_PATH = "data/metro/hh_metro.json"
MATRIX_PATH = "data/metro/station_matrix.npy"
STATIONS_PATH = "data/metro/station_list.json"
GRID_PATH = "data/metro/grid_walk_to_metro.json"

_cache = {}


def to_km(latlon):
    a = np.asarray(latlon, dtype=float).reshape(-1, 2)
    return np.column_stack([a[:, 0] * KM_LAT, a[:, 1] * KM_LON])


def walk_minutes(km):
    return km * WALK_DETOUR / WALK_KMH * 60


def load_graph():
    with open(META_PATH, encoding="utf-8") as f:
        meta = json.load(f)
    stations = []
    edges = []
    for line in meta["lines"]:
        lid = line["id"]
        members = sorted(line["stations"], key=lambda s: s["order"])
        idx = []
        for s in members:
            idx.append(len(stations))
            stations.append({"id": s["id"], "name": s["name"], "lat": s["lat"], "lng": s["lng"], "line": lid, "line_name": line["name"]})
        pairs = list(zip(idx[:-1], idx[1:]))
        if lid in RING_LINES:
            first, last = stations[idx[0]], stations[idx[-1]]
            gap = np.hypot((first["lat"] - last["lat"]) * KM_LAT, (first["lng"] - last["lng"]) * KM_LON)
            if gap < RING_MAX_KM:
                pairs.append((idx[-1], idx[0]))
        for a, b in pairs:
            sa, sb = stations[a], stations[b]
            km = np.hypot((sa["lat"] - sb["lat"]) * KM_LAT, (sa["lng"] - sb["lng"]) * KM_LON)
            m = km / SPEED * 60 + DWELL
            edges.append((a, b, m))
            edges.append((b, a, m))
    xy = to_km([[s["lat"], s["lng"]] for s in stations])
    tree = cKDTree(xy)
    for a, b in sorted(tree.query_pairs(TRANSFER_MAX_KM)):
        if stations[a]["line"] == stations[b]["line"]:
            continue
        km = float(np.hypot(*(xy[a] - xy[b])))
        m = TRANSFER_BASE + max(0.0, km - TRANSFER_FREE_KM) / 0.1
        edges.append((a, b, m))
        edges.append((b, a, m))
    n = len(stations)
    rows, cols, vals = zip(*edges)
    mat = coo_matrix((vals, (rows, cols)), shape=(n, n)).tocsr()
    return {"stations": stations, "adj": mat, "xy": xy}


def station_times(graph):
    if os.path.exists(MATRIX_PATH) and os.path.exists(STATIONS_PATH):
        with open(STATIONS_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        if [s["id"] for s in saved] == [s["id"] for s in graph["stations"]]:
            return np.load(MATRIX_PATH)
    dist = dijkstra(graph["adj"], directed=True)
    dist = dist + BOARD_WAIT
    np.fill_diagonal(dist, 0.0)
    dist = dist.astype(np.float32)
    np.save(MATRIX_PATH, dist)
    with open(STATIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(graph["stations"], f, ensure_ascii=False)
    return dist


def _state():
    if not _cache:
        graph = load_graph()
        _cache["graph"] = graph
        _cache["matrix"] = station_times(graph)
        _cache["tree"] = cKDTree(graph["xy"])
    return _cache


def _access(tree, xy):
    d, i = tree.query(xy, k=ACCESS_K, distance_upper_bound=ACCESS_MAX_KM)
    ok = np.isfinite(d)
    idx = np.where(ok, i, 0)
    w = np.where(ok, walk_minutes(np.where(ok, d, 0.0)), np.inf)
    return idx, w


def door_to_door(orig_latlon_array, dest_latlon_array, chunk=1000):
    st = _state()
    mat = st["matrix"]
    tree = st["tree"]
    o_xy = to_km(orig_latlon_array)
    d_xy = to_km(dest_latlon_array)
    d_idx, d_w = _access(tree, d_xy)
    out = np.empty((len(o_xy), len(d_xy)), dtype=np.float32)
    for s in range(0, len(o_xy), chunk):
        part = o_xy[s:s + chunk]
        o_idx, o_w = _access(tree, part)
        reach = np.full((len(part), mat.shape[0]), np.inf, dtype=np.float32)
        for k in range(ACCESS_K):
            reach = np.minimum(reach, o_w[:, k:k + 1] + mat[o_idx[:, k]])
        best = np.full((len(part), len(d_xy)), np.inf, dtype=np.float32)
        for k in range(ACCESS_K):
            best = np.minimum(best, reach[:, d_idx[:, k]] + d_w[:, k][None, :])
        direct = walk_minutes(np.hypot(part[:, None, 0] - d_xy[None, :, 0], part[:, None, 1] - d_xy[None, :, 1]))
        out[s:s + chunk] = np.minimum(best, direct)
    return out


def grid_walk_to_metro():
    st = _state()
    nlat = int(np.ceil((LAT1 - LAT0) / DLAT - 1e-9))
    nlon = int(np.ceil((LON1 - LON0) / DLON - 1e-9))
    lats = LAT0 + (np.arange(nlat) + 0.5) * DLAT
    lons = LON0 + (np.arange(nlon) + 0.5) * DLON
    cells = np.array([[a, b] for a in lats for b in lons])
    d, _ = st["tree"].query(to_km(cells))
    values = np.round(walk_minutes(d), 1).reshape(nlat, nlon)
    with open(GRID_PATH, "w", encoding="utf-8") as f:
        json.dump({"lat0": LAT0, "lon0": LON0, "dlat": DLAT, "dlon": DLON, "nlat": nlat, "nlon": nlon, "values": values.tolist()}, f)


if __name__ == "__main__":
    grid_walk_to_metro()
    g = _state()["graph"]
    names = {}
    for s in g["stations"]:
        names.setdefault(s["name"], []).append((s["lat"], s["lng"]))
    checks = [("Сокольники", "Охотный ряд"), ("Измайловская", "Арбатская"), ("Сокол", "Курская")]
    for a, b in checks:
        t = door_to_door([names[a][0]], [names[b][0]])
        print(a, b, np.round(t, 1))
    rng = np.random.default_rng(0)
    o = np.column_stack([rng.uniform(55.55, 55.92, 12000), rng.uniform(37.35, 37.86, 12000)])
    d = np.column_stack([rng.uniform(55.6, 55.9, 500), rng.uniform(37.4, 37.8, 500)])
    t0 = time.time()
    r = door_to_door(o, d)
    print("bench", r.shape, round(time.time() - t0, 1), "s", float(np.median(r)))

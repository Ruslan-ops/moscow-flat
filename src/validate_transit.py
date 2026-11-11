import json
import re
import sys
import time
import numpy as np
from scipy.sparse.csgraph import dijkstra

sys.path.insert(0, "d:/Users/Ruslan/VsCodeProjects/moscow-flat/src")
import transit
import dgis_cache

ENV = "d:/Users/Ruslan/VsCodeProjects/moscow-flat/.env"
OUT_PATH = "data/metro/validation_2gis.json"
MAX_CALLS = 70
COUNT_PATH = "data/metro/dgis_routing_count.txt"
HUBS_PATH = "data/jobs/creative_hubs.json"
TRANSPORT = ["metro", "bus", "tram", "trolleybus", "light_metro", "suburban_train", "shuttle_bus"]
CENTRAL = [(55.7558, 37.6176), (55.7539, 37.6208), (55.7603, 37.6186), (55.7447, 37.6053), (55.7653, 37.6256)]
N_NEAR = 30
N_FAR = 30
FAR_WALK_MIN = 15.0


def key():
    for line in open(ENV, encoding="utf-8"):
        if line.startswith("DGIS_KEY_PT="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")


def build_pairs():
    rng = np.random.default_rng(42)
    hubs = json.load(open(HUBS_PATH, encoding="utf-8"))
    dests = [(h["lat"], h["lng"], h["name"]) for h in hubs] + [(a, b, "central") for a, b in CENTRAL]
    tree = transit._state()["tree"]
    near, far = [], []
    while len(near) < N_NEAR or len(far) < N_FAR:
        ang = rng.uniform(0, 2 * np.pi)
        r = 14.0 * np.sqrt(rng.uniform())
        lat = 55.7558 + r * np.sin(ang) / transit.KM_LAT
        lon = 37.6176 + r * np.cos(ang) / transit.KM_LON
        d, _ = tree.query(transit.to_km([[lat, lon]]))
        walk = float(transit.walk_minutes(d[0]))
        d_lat, d_lon, d_name = dests[rng.integers(len(dests))]
        pair = {"o_lat": lat, "o_lng": lon, "d_lat": d_lat, "d_lng": d_lon, "d_name": d_name, "origin_walk_to_metro_min": round(walk, 1)}
        if walk <= 10 and len(near) < N_NEAR:
            near.append(pair)
        elif 15 <= walk <= 30 and len(far) < N_FAR:
            far.append(pair)
    return near + far


def route(p, k, run):
    body = {"source": {"name": "a", "point": {"lat": p["o_lat"], "lon": p["o_lng"]}}, "target": {"name": "b", "point": {"lat": p["d_lat"], "lon": p["d_lng"]}}, "transport": TRANSPORT, "locale": "ru"}
    if run["calls"] >= MAX_CALLS:
        raise SystemExit("run cap reached")
    j, real = dgis_cache.cached("POST", "https://routing.api.2gis.com/public_transport/2.0", body=body, key=k)
    if real:
        run["calls"] += 1
        n = int(open(COUNT_PATH).read()) + 1
        open(COUNT_PATH, "w").write(str(n))
        time.sleep(13)
    if not isinstance(j, list) or not j:
        return None
    return min(j, key=lambda a: a["total_duration"])["total_duration"] / 60


def fetch():
    k = key()
    run = {"calls": 0}
    pairs = build_pairs()
    done = []
    try:
        for p in pairs:
            p["dgis_min"] = route(p, k, run)
            done.append(p)
    except SystemExit as e:
        print("stopped", e)
    json.dump(done, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False)
    return done


def engine_times(pairs):
    return np.array([transit.door_to_door([[p["o_lat"], p["o_lng"]]], [[p["d_lat"], p["d_lng"]]])[0, 0] for p in pairs])


def set_constants(**kw):
    for k, v in kw.items():
        setattr(transit, k, v)
    transit._cache.clear()
    g = transit.load_graph()
    dist = dijkstra(g["adj"], directed=True) + transit.BOARD_WAIT
    np.fill_diagonal(dist, 0.0)
    transit._cache.update({"graph": g, "matrix": dist.astype(np.float32), "tree": transit.cKDTree(g["xy"])})


def metrics(pairs, ours):
    ref = np.array([p["dgis_min"] for p in pairs])
    walk = np.array([p["origin_walk_to_metro_min"] for p in pairs])
    out = {}
    for name, m in [("all", np.ones(len(pairs), bool)), ("near", walk < FAR_WALK_MIN), ("far", walk >= FAR_WALK_MIN)]:
        e = ours[m] - ref[m]
        out[name] = {"n": int(m.sum()), "median_err": round(float(np.median(e)), 1), "mae": round(float(np.mean(np.abs(e))), 1), "bias": round(float(np.mean(e)), 1), "ratio": round(float(np.median(ours[m] / ref[m])), 2)}
    return out


def tune(pairs):
    ok = [p for p in pairs if p["dgis_min"] is not None and np.isfinite(p["dgis_min"])]
    near = [p for p in ok if p["origin_walk_to_metro_min"] < FAR_WALK_MIN]
    ref = np.array([p["dgis_min"] for p in near])
    best = None
    for speed in [32.0, 36.0, 40.0, 45.0]:
        for wait in [1.0, 2.0, 3.0, 4.5]:
            for detour in [1.1, 1.2, 1.3]:
                for tb in [3.0, 4.5, 6.0]:
                    set_constants(SPEED=speed, BOARD_WAIT=wait, WALK_DETOUR=detour, TRANSFER_BASE=tb)
                    mae = float(np.mean(np.abs(engine_times(near) - ref)))
                    if best is None or mae < best[0]:
                        best = (mae, speed, wait, detour, tb)
    return best


def write_constants(speed, wait, detour, tb):
    src = open("src/transit.py", encoding="utf-8").read()
    for name, v in [("SPEED", speed), ("BOARD_WAIT", wait), ("WALK_DETOUR", detour), ("TRANSFER_BASE", tb)]:
        src = re.sub(rf"^{name} = .*$", f"{name} = {v}", src, flags=re.M)
    open("src/transit.py", "w", encoding="utf-8").write(src)


if __name__ == "__main__":
    mode = sys.argv[1]
    pairs = json.load(open(OUT_PATH, encoding="utf-8")) if mode != "fetch" else fetch()
    pairs = [p for p in pairs if p["dgis_min"] is not None]
    if mode in ("fetch", "eval"):
        ours = engine_times(pairs)
        for p, o in zip(pairs, ours):
            p["our_min"] = round(float(o), 1)
        print("before", json.dumps(metrics(pairs, ours)))
        worst = sorted(pairs, key=lambda p: -abs(p["our_min"] - p["dgis_min"]))[:5]
        for p in worst:
            print("worst", p["d_name"], p["origin_walk_to_metro_min"], p["our_min"], round(p["dgis_min"], 1))
        json.dump(pairs, open(OUT_PATH, "w", encoding="utf-8"), ensure_ascii=False)
    if mode == "tune":
        best = tune(pairs)
        print("best", best)
        set_constants(SPEED=best[1], BOARD_WAIT=best[2], WALK_DETOUR=best[3], TRANSFER_BASE=best[4])
        print("after", json.dumps(metrics(pairs, engine_times(pairs))))

import sys
import numpy as np
sys.path.insert(0, __file__.replace("\\", "/").rsplit("/", 1)[0])
from layers import LAYERS_DIR, noise_distances, save_grid
from transit import LAT0, LON0, DLAT, DLON

MATERIALS = {"brick": 1.0, "stalin": 1.0, "monolithBrick": 0.9, "monolith": 0.75, "block": 0.6, "wood": 0.3, "panel": 0.35}
WALK_MAX = 15
HUBS = [(55.776, 37.655), (55.757, 37.661), (55.743, 37.566), (55.776, 37.581), (55.730, 37.640), (55.794, 37.589), (55.793, 37.633), (55.757, 37.615), (55.654, 37.754), (55.676, 37.762)]
ENSEMBLES = [(55.826, 37.637), (55.727, 37.582), (55.707, 37.585), (55.741, 37.535), (55.801, 37.505), (55.718, 37.608), (55.764, 37.639), (55.763, 37.592), (55.718, 37.674), (55.727, 37.566)]
RED_FLAGS = {"предоплат": "prepayment", "без просмотра": "no_viewing", "только славян": "discriminatory", "посуточно": "daily_rent", "на короткий срок": "short_term", "сдается комната": "room", "сдаётся комната": "room", "комната в квартире": "room", "койко": "room", "долю ": "room", "доля в квартире": "room"}
GOOD_TAGS = ["собственник", "без комиссии", "тихий", "сталин", "высокие потолки", "парк", "кирпич"]
_state = {}


def load_layers():
    if not _state:
        with np.load(f"{LAYERS_DIR}/all.npz") as z:
            _state["layers"] = {k: z[k] for k in z.files}
    return _state["layers"]


def ramp(x, full, zero):
    return np.clip((zero - x) / (zero - full), 0, 1)


def cell_components(layers):
    near = layers["walk_metro"] <= WALK_MAX
    job_raw = layers["job_share30"] * 0.6 + layers["job_share40"] * 0.4
    culture_ref = np.log1p(np.percentile(layers["culture25"][near], 95))
    return {
        "job": np.clip(job_raw / np.percentile(job_raw[near], 95), 0, 1),
        "park": ramp(layers["park_walk"], 8, 25),
        "culture": np.clip(np.log1p(layers["culture25"]) / culture_ref, 0, 1),
        "metro": ramp(layers["walk_metro"], 7, 15),
    }


def cell_score(layers):
    c = cell_components(layers)
    score = 0.35 * c["job"] + 0.25 * c["park"] + 0.2 * c["metro"] + 0.2 * c["culture"]
    return np.where(layers["walk_metro"] > WALK_MAX, 0.0, score)


def cell_index(lat, lng, shape):
    i = int(np.clip((lat - LAT0) // DLAT, 0, shape[0] - 1))
    j = int(np.clip((lng - LON0) // DLON, 0, shape[1] - 1))
    return i, j


def heat():
    if "heat" not in _state:
        _state["heat"] = cell_score(load_layers())
    return _state["heat"]


def heat_percentile(value):
    if "heat_sorted" not in _state:
        _state["heat_sorted"] = np.sort(heat()[load_layers()["walk_metro"] <= WALK_MAX])
    return float(np.searchsorted(_state["heat_sorted"], value, side="right") / len(_state["heat_sorted"]))


def haversine_m(lat1, lng1, lat2, lng2):
    a = np.sin(np.radians(lat2 - lat1) / 2) ** 2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(np.radians(lng2 - lng1) / 2) ** 2
    return 12742000 * np.arcsin(np.sqrt(a))


def near_any(points, lat, lng, radius):
    return any(haversine_m(lat, lng, p[0], p[1]) <= radius for p in points)


def description_flags(text):
    low = (text or "").lower()
    return [v for k, v in RED_FLAGS.items() if k in low], [k.replace(" ", "_") for k in GOOD_TAGS if k in low]


def num(x):
    return None if x in (None, "") else float(x)


def floor_score(floor, floors):
    s = 1.0 if floor <= 5 else 0.85 if floor <= 9 else 0.6 if floor <= 14 else 0.35
    return s - 0.1 if floors and floor == floors else s


def building_score(material, year):
    s = MATERIALS.get(material, 0.5)
    if year and 1930 <= year <= 1958:
        s += 0.15
    if material == "panel" and year and 1960 <= year <= 1975:
        s -= 0.1
    return float(np.clip(s, 0, 1))


def quiet_score(d):
    road = min(d["noise_dist"], d["primary_dist"])
    s = 0.35 if road < 45 else 0.7 if road < 100 else 1.0
    if d["noise_dist"] < 150:
        s -= 0.15
    s -= 0.3 if d["rail_dist"] < 100 else 0.1 if d["rail_dist"] < 200 else 0
    return float(np.clip(s, 0, 1))


def price_score(price, utilities_included):
    s = float(np.interp(price, [55000, 62000, 70000], [1.0, 0.5, 0.2]))
    return min(1.0, s + 0.05) if utilities_included else s


def reject(reason):
    return {"rejected": True, "reason": reason}


def listing_score(o, layers, ratio=None):
    bt = o.get("bargainTerms") or {}
    b = o.get("building") or {}
    geo = o.get("geo") or {}
    price = num(bt.get("price"))
    area = num(o.get("totalArea"))
    floor = o.get("floorNumber")
    floors = b.get("floorsCount")
    lifts = b.get("passengerLiftsCount")
    metro = min(((u["time"], u["name"]) for u in geo.get("undergrounds") or [] if u.get("transportType") == "walk" and u.get("time") is not None), default=None)
    lat = geo["coordinates"]["lat"]
    lng = geo["coordinates"]["lng"]
    i, j = cell_index(lat, lng, layers["walk_metro"].shape)
    walk = metro[0] if metro else float(layers["walk_metro"][i, j])
    if o.get("isApartments"):
        return reject("apartments")
    if area is None or area < 29:
        return reject("area<29")
    if price is None or price > 70000:
        return reject("price>70k")
    if floor == 1:
        return reject("floor1")
    if floor is not None and floor > 4 and lifts == 0:
        return reject("no_lift")
    if walk > WALK_MAX:
        return reject("metro>15")
    if bt.get("leaseTermType") != "longTerm":
        return reject("not_longTerm")
    flags = []
    if floor is not None and floor > 4 and lifts is None:
        flags.append("lift_assumed" if floors and floors >= 6 else "lift_unknown")
    noise = {k: float(v[0]) for k, v in noise_distances([[lat, lng]]).items()}
    owner = bool(o.get("isByHomeowner")) or (o.get("user") or {}).get("isAgent") is False
    fee_pct = bt.get("clientFee") if bt.get("clientFee") is not None else bt.get("agentFee")
    kitchen = num(o.get("kitchenArea"))
    red, tags = description_flags(o.get("description"))
    flags += list(dict.fromkeys(red))
    job_p50 = float(layers["job_p50"][i, j])
    soft = "room_or_share" if "room" in red else None
    adj = 0.0
    if ratio is not None and ratio < 0.72:
        flags.append("suspiciously_cheap")
        adj -= 0.25
    if ratio is not None and ratio < 0.6:
        flags.append("likely_bait")
        soft = soft or "likely_bait"
    if job_p50 > 50:
        adj -= 0.1
    if job_p50 <= 35:
        adj += 0.05
    if near_any(HUBS, lat, lng, 450):
        flags.append("crowded_hub")
        adj -= 0.1
    year = b.get("buildYear")
    if year and 1935 <= year <= 1958 and b.get("materialType") in ("brick", "stalin", None) and floors and 5 <= floors <= 12:
        tags.append("stalinka")
        adj += 0.06
    if near_any(ENSEMBLES, lat, lng, 1000):
        tags.append("soviet_ensemble")
        adj += 0.04
    price_abs = price_score(price, (bt.get("utilitiesTerms") or {}).get("includedInPrice"))
    comp = {
        "location": heat_percentile(heat()[i, j]),
        "building": building_score(b.get("materialType"), b.get("buildYear")),
        "floor": floor_score(floor, floors) if floor else 0.5,
        "quiet": quiet_score(noise),
        "price_value": price_abs if ratio is None else float(np.clip(1.25 - ratio * 0.5, 0, 1)) * 0.5 + price_abs * 0.5,
    }
    bonus = 0.05 * owner + 0.05 * (area >= 36) + 0.05 * (kitchen is not None and kitchen >= 8)
    if owner:
        flags.append("owner")
    total = min(1.0, 0.35 * comp["location"] + 0.2 * comp["building"] + 0.1 * comp["floor"] + 0.15 * comp["quiet"] + 0.2 * comp["price_value"] + bonus + adj)
    total = 0.0 if soft else max(0.0, total)
    return {
        "rejected": False,
        "components": comp,
        "bonus": bonus,
        "flags": flags,
        "tags": tags,
        "soft_reject": soft,
        "price_ratio": None if ratio is None else float(ratio),
        "total": float(total),
        "noise": noise,
        "move_in_cost": price + (num(bt.get("deposit")) or 0) + price * (num(fee_pct) or 0) / 100,
        "metro": metro[1] if metro else None,
        "metro_walk": walk,
        "job_p50": job_p50,
        "job_share30": float(layers["job_share30"][i, j]),
        "park_walk": float(layers["park_walk"][i, j]),
        "culture25": int(layers["culture25"][i, j]),
        "tier": "A" if price <= 62000 else "B",
    }


def main():
    h = heat()
    save_grid("heat", h)
    print("heat", float(h.min()), float(np.percentile(h[h > 0], 50)), float(h.max()))
    layers = load_layers()
    for name, lat, lng in [("sokolniki", 55.792, 37.676), ("izmailovo", 55.788, 37.749), ("butovo", 55.545, 37.57), ("khamovniki", 55.73, 37.58), ("mitino", 55.845, 37.36), ("center", 55.7558, 37.6173)]:
        i, j = cell_index(lat, lng, h.shape)
        print(name, round(float(h[i, j]), 3), "walk", float(layers["walk_metro"][i, j]), "p50", round(float(layers["job_p50"][i, j]), 1), "share30", round(float(layers["job_share30"][i, j]), 3), "park", round(float(layers["park_walk"][i, j]), 1), "cult", int(layers["culture25"][i, j]))


if __name__ == "__main__":
    main()

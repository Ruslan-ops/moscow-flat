import glob
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime

sys.path.insert(0, "D:/Users/Ruslan/VsCodeProjects/moscow-flat/src")
from realtor import days_listed

ROOT = "D:/Users/Ruslan/VsCodeProjects/moscow-flat"
PY = f"{ROOT}/.venv/Scripts/python.exe"
DB = f"{ROOT}/data/avito/collector.sqlite"
NEW = f"{ROOT}/data/reviews/new"
SEARCHES = [f"{ROOT}/data/cian/search_urls_v2.txt", f"{ROOT}/data/cian/search_urls_repair.txt"]
MAX_AGE_DAYS = 100
BATCH = 12


def run(*args):
    subprocess.run([PY, "-X", "utf8", "-I", *args], check=True)


def load(path):
    return json.load(open(f"{ROOT}/{path}", encoding="utf-8"))


def dump(obj, path):
    json.dump(obj, open(f"{ROOT}/{path}", "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def reviewed_ids():
    return {r["cianId"] for path in ("data/reviews/all_sonnet.json", "data/reviews/align_opus.json") for r in load(path)}


def repair_ids():
    conn = sqlite3.connect(DB)
    ids = {int(r[0]) for r in conn.execute("SELECT cian_id FROM cian_tags WHERE tag = 'repair'")}
    conn.close()
    return ids | set(load("data/cian/repair_euro_design_ids.json"))


def seed():
    for path in SEARCHES:
        run(f"{ROOT}/collector/server.py", "seed-cian-refresh", path)
    shown = load("data/report/finalist_ids.json") if os.path.exists(f"{ROOT}/data/report/finalist_ids.json") else []
    dump(shown, "data/report/check_ids.json")
    run(f"{ROOT}/collector/server.py", "seed-cian-items", f"{ROOT}/data/report/check_ids.json")


def queue_status():
    conn = sqlite3.connect(DB)
    rows = conn.execute("SELECT type, status, count(*) FROM tasks WHERE type LIKE 'cian_%' AND status IN ('queued', 'in_progress') GROUP BY type, status").fetchall()
    conn.close()
    print(rows or "queue empty")


def prepare(limit, max_price):
    run(f"{ROOT}/src/cian_export.py")
    run(f"{ROOT}/src/rank.py")
    done = reviewed_ids()
    repair = repair_ids()
    ranked = load("data/ranked/cian_ranked.json")
    offers = {o["cianId"]: o for o in load("data/cian/offers.json")}
    cand = [r for r in ranked if not r["soft_reject"] and not r.get("duplicate_of") and r["cianId"] not in done and r["cianId"] in repair and r["price"] <= max_price and (days_listed(offers[r["cianId"]], datetime.now()) or 0) <= MAX_AGE_DAYS]
    seen = {o["cianId"]: o["first_seen"] for o in load("data/cian/offers.json")}
    since = max(seen[i] for i in done if i in seen)
    cand.sort(key=lambda r: (seen[r["cianId"]] <= since, -r["total"]))
    picked = [r["cianId"] for r in cand[:limit]]
    print("unreviewed candidates", len(cand), "new since", since, sum(seen[r["cianId"]] > since for r in cand), "picked", len(picked), "with repair tag", sum(r["cianId"] in repair for r in cand[:limit]))
    if not picked:
        return
    for f in glob.glob(f"{NEW}/*.json"):
        os.remove(f)
    os.makedirs(NEW, exist_ok=True)
    dump(picked, "data/reviews/new/queue.json")
    run(f"{ROOT}/src/photos.py", "offers", f"{NEW}/queue.json")
    have = [i for i in picked if os.path.exists(f"{ROOT}/data/photos/full/{i}.jpg")]
    for k in range(0, len(have), BATCH):
        dump([{"cianId": i, "price": offers[i]["bargainTerms"]["price"], "area": offers[i].get("totalArea"), "kitchen": offers[i].get("kitchenArea"), "rooms": offers[i].get("roomsCount"), "floor": f"{offers[i].get('floorNumber')}/{offers[i]['building'].get('floorsCount')}", "photos_total": len(offers[i].get("photos") or []), "description": (offers[i].get("description") or "")[:1500]} for i in have[k:k + BATCH]], f"data/reviews/new/batch_{k // BATCH}.json")
    print("batches", (len(have) + BATCH - 1) // BATCH, "in", NEW)


def merge():
    store = load("data/reviews/all_sonnet.json")
    known = {r["cianId"] for r in store}
    added = [r for f in sorted(glob.glob(f"{NEW}/out_*.json")) for r in json.load(open(f, encoding="utf-8-sig")) if r["cianId"] not in known]
    stamp = datetime.now().strftime("%Y-%m-%d")
    for r in added:
        r["reviewed"] = stamp
    dump(store + added, "data/reviews/all_sonnet.json")
    print("merged", len(added), "total", len(store) + len(added), "pred>=4", sum(r["pred"] >= 4 for r in added), "pred>=3.5", sum(r["pred"] >= 3.5 for r in added))


def build():
    run(f"{ROOT}/src/finalists.py")
    run(f"{ROOT}/src/build_report.py")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "seed":
        seed()
    elif cmd == "status":
        queue_status()
    elif cmd == "prepare":
        prepare(int(sys.argv[2]) if len(sys.argv) > 2 else 48, int(sys.argv[3]) if len(sys.argv) > 3 else 70000)
    elif cmd == "merge":
        merge()
    elif cmd == "build":
        build()

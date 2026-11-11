import json
import sqlite3

ROOT = __file__.replace("\\", "/").rsplit("/src/", 1)[0]
DB_PATH = f"{ROOT}/data/avito/collector.sqlite"
OUT_PATH = f"{ROOT}/data/cian/offers.json"

conn = sqlite3.connect(DB_PATH)
rows = []
for cian_id, payload, first_seen, last_seen in conn.execute("SELECT cian_id, json, first_seen, last_seen FROM cian_offers ORDER BY cian_id"):
    rec = json.loads(payload)
    rec.update({"first_seen": first_seen, "last_seen": last_seen})
    rows.append(rec)
conn.close()
with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=1)
print("offers", len(rows))

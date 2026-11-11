import json
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
DATA_DIR = f"{ROOT}/data/avito"
DB_PATH = f"{DATA_DIR}/collector.sqlite"


def dump(conn, sql, out_name, extra):
    rows = []
    for row in conn.execute(sql):
        rec = json.loads(row[1])
        rec.update({k: row[i] for k, i in extra.items()})
        rows.append(rec)
    with open(f"{DATA_DIR}/{out_name}.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    print(out_name, len(rows))


conn = sqlite3.connect(DB_PATH)
dump(conn, "SELECT item_id, json, first_seen, last_seen FROM search_cards ORDER BY item_id", "cards", {"first_seen": 2, "last_seen": 3})
dump(conn, "SELECT item_id, json, fetched_at FROM items ORDER BY item_id", "items", {"fetched_at": 2})
conn.close()

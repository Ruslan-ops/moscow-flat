import hashlib
import json
import requests

CACHE_DIR = "data/cache/dgis"


def cached(method, url, params=None, body=None, key=None, timeout=60):
    clean = {k: v for k, v in (params or {}).items() if k != "key"}
    h = hashlib.sha1(json.dumps([method, url, clean, body], sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    path = f"{CACHE_DIR}/{h}.json"
    try:
        return json.load(open(path, encoding="utf-8")), False
    except FileNotFoundError:
        pass
    full = {**clean, "key": key}
    if method == "GET":
        r = requests.get(url, params=full, timeout=timeout)
    else:
        r = requests.post(f"{url}?key={key}", json=body, timeout=timeout)
    if r.status_code in (403, 429):
        raise SystemExit(f"limit error {r.status_code}")
    data = r.json()
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    return data, True

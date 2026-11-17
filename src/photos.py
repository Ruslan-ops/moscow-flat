import base64
import io
import json
import os
import sys
import time
import requests
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

ROOT = "D:/Users/Ruslan/VsCodeProjects/moscow-flat"
TILE_W, TILE_H, COLS = 320, 240, 4
FULL_TILE, FULL_MAX = (400, 300), 28


def fetch(url):
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                return Image.open(io.BytesIO(r.content)).convert("RGB")
            if r.status_code in (403, 404):
                return None
        except requests.RequestException:
            pass
        time.sleep(3 * (attempt + 1))
    return None


def montage(images, path, tile=(TILE_W, TILE_H)):
    w, h = tile
    rows = (len(images) + COLS - 1) // COLS
    sheet = Image.new("RGB", (w * COLS, h * rows), "white")
    for i, im in enumerate(images):
        im.thumbnail((w, h))
        sheet.paste(im, ((i % COLS) * w + (w - im.width) // 2, (i // COLS) * h + (h - im.height) // 2))
    sheet.save(path, "JPEG", quality=80)


def pick(urls, n):
    return urls if len(urls) <= n else [urls[round(i * (len(urls) - 1) / (n - 1))] for i in range(n)]


def sheet_for_offer(offer, max_photos=12, path=None, tile=(TILE_W, TILE_H)):
    imgs = [im for im in (fetch(u) for u in pick(offer.get("photos", []), max_photos)) if im is not None]
    if imgs:
        montage(imgs, path or f"{ROOT}/data/photos/{offer['cianId']}.jpg", tile)
    return len(imgs)


def sheets_for_offer(offer):
    full = pick(offer.get("photos", []), FULL_MAX)
    with ThreadPoolExecutor(4) as ex:
        got = dict(zip(full, ex.map(fetch, full)))
    imgs = [got[u] for u in full if got[u] is not None]
    if imgs:
        montage([im.copy() for im in imgs], f"{ROOT}/data/photos/full/{offer['cianId']}.jpg", FULL_TILE)
        montage(pick(imgs, 12), f"{ROOT}/data/photos/{offer['cianId']}.jpg")
    return len(imgs), len(full)


def calib_sheets():
    for n, it in enumerate(json.load(open(f"{ROOT}/scratch/calib.json", encoding="utf-8")), 1):
        imgs = [Image.open(io.BytesIO(base64.b64decode(s.split(",", 1)[1]))).convert("RGB") for s in it["imgs"]]
        montage(imgs, f"{ROOT}/data/calib/{n}_{it['cianId']}.jpg")


if __name__ == "__main__":
    if sys.argv[1] == "calib":
        calib_sheets()
    else:
        offers = {o["cianId"]: o for o in json.load(open(f"{ROOT}/data/cian/offers.json", encoding="utf-8"))}
        os.makedirs(f"{ROOT}/data/photos/full", exist_ok=True)
        for cid in json.load(open(sys.argv[2], encoding="utf-8")):
            if not os.path.exists(f"{ROOT}/data/photos/full/{cid}.jpg"):
                print(cid, *sheets_for_offer(offers[cid]), flush=True)

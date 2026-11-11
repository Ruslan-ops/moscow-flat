import base64
import io
import json
import sys
import requests
from PIL import Image

ROOT = "D:/Users/Ruslan/VsCodeProjects/moscow-flat"
TILE_W, TILE_H, COLS = 320, 240, 4


def fetch(url):
    r = requests.get(url, timeout=30)
    return Image.open(io.BytesIO(r.content)).convert("RGB") if r.status_code == 200 else None


def montage(images, path):
    rows = (len(images) + COLS - 1) // COLS
    sheet = Image.new("RGB", (TILE_W * COLS, TILE_H * rows), "white")
    for i, im in enumerate(images):
        im.thumbnail((TILE_W, TILE_H))
        sheet.paste(im, ((i % COLS) * TILE_W + (TILE_W - im.width) // 2, (i // COLS) * TILE_H + (TILE_H - im.height) // 2))
    sheet.save(path, "JPEG", quality=80)


def sheet_for_offer(offer, max_photos=12):
    urls = offer.get("photos", [])
    picked = urls if len(urls) <= max_photos else [urls[round(i * (len(urls) - 1) / (max_photos - 1))] for i in range(max_photos)]
    imgs = [im for im in (fetch(u) for u in picked) if im is not None]
    if imgs:
        montage(imgs, f"{ROOT}/data/photos/{offer['cianId']}.jpg")
    return len(imgs)


def calib_sheets():
    for n, it in enumerate(json.load(open(f"{ROOT}/scratch/calib.json", encoding="utf-8")), 1):
        imgs = [Image.open(io.BytesIO(base64.b64decode(s.split(",", 1)[1]))).convert("RGB") for s in it["imgs"]]
        montage(imgs, f"{ROOT}/data/calib/{n}_{it['cianId']}.jpg")


if __name__ == "__main__":
    if sys.argv[1] == "calib":
        calib_sheets()
    else:
        offers = {o["cianId"]: o for o in json.load(open(f"{ROOT}/data/cian/offers.json", encoding="utf-8"))}
        for cid in json.load(open(sys.argv[2], encoding="utf-8")):
            print(cid, sheet_for_offer(offers[cid]))

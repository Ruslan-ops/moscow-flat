import base64
import json
import requests
cands = json.load(open("D:/Users/Ruslan/VsCodeProjects/moscow-flat/data/ranked/shortlist_candidates.json", encoding="utf-8"))
offers = {o["cianId"]: o for o in json.load(open("D:/Users/Ruslan/VsCodeProjects/moscow-flat/data/cian/offers.json", encoding="utf-8"))}
step = max(1, len(cands) // 10)
picked = [cands[i] for i in range(0, len(cands), step)][:10]
out = []
for c in picked:
    o = offers[c["cianId"]]
    imgs = []
    for u in o.get("photos", [])[:3]:
        r = requests.get(u, timeout=30)
        if r.status_code == 200:
            imgs.append(f"data:{r.headers.get('content-type', 'image/jpeg')};base64,{base64.b64encode(r.content).decode()}")
    out.append({"cianId": c["cianId"], "url": c["fullUrl"].split("?")[0], "price": c["price"], "area": c["totalArea"], "floor": f"{c['floorNumber']}/{c['floorsCount']}", "metro": c["metro"], "imgs": imgs})
    print(c["cianId"], len(imgs))
json.dump(out, open("D:/Users/Ruslan/VsCodeProjects/moscow-flat/scratch/calib.json", "w", encoding="utf-8"), ensure_ascii=False)

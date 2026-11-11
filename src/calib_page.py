import html
import json

items = json.load(open("D:/Users/Ruslan/VsCodeProjects/moscow-flat/scratch/calib.json", encoding="utf-8"))
tpl = open("D:/Users/Ruslan/VsCodeProjects/moscow-flat/src/calib_template.html", encoding="utf-8").read()
cards = []
for n, it in enumerate(items, 1):
    imgs = "".join(f'<img src="{s}" alt="Квартира {n}, фото {k + 1}" loading="lazy">' for k, s in enumerate(it["imgs"]))
    btns = "".join(f'<button type="button" data-n="{n}" data-v="{v}">{v}</button>' for v in range(1, 6))
    price = f"{it['price']:,}".replace(",", " ")
    cards.append(f'<article class="flat" id="flat-{n}"><header><span class="num">{n}</span><span class="meta">{price} ₽ · {it["area"]} м² · этаж {it["floor"]} · м. {html.escape(str(it["metro"]))}</span><a href="{it["url"]}" target="_blank" rel="noopener">ЦИАН ↗</a></header><div class="photos">{imgs}</div><div class="rate" role="group" aria-label="Оценка квартиры {n}">{btns}</div><input id="note-{n}" class="note" placeholder="Что нравится или что не так (необязательно)"></article>')
open("D:/Users/Ruslan/VsCodeProjects/moscow-flat/report/calibration.html", "w", encoding="utf-8").write(tpl.replace("{{CARDS}}", "".join(cards)).replace("{{N}}", str(len(items))))

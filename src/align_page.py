import base64
import html
import json

ROOT = "D:/Users/Ruslan/VsCodeProjects/moscow-flat"
ranked = {x["cianId"]: x for x in json.load(open(f"{ROOT}/data/ranked/cian_ranked.json", encoding="utf-8"))}
offers = {o["cianId"]: o for o in json.load(open(f"{ROOT}/data/cian/offers.json", encoding="utf-8"))}
reviews = json.load(open(f"{ROOT}/data/reviews/align_opus.json", encoding="utf-8"))
MATERIAL = {"brick": "кирпич", "stalin": "сталинский", "monolithBrick": "монолит-кирпич", "monolith": "монолит", "block": "блочный", "panel": "панель", "wood": "дерево"}
VERDICT = {"смотреть": "good", "запасной": "mid", "под вопросом": "mid", "нет": "bad"}


def money(v):
    return f"{int(v):,}".replace(",", " ")


def quiet_label(q):
    return "тихо" if q >= 0.95 else "умеренно" if q >= 0.6 else "шумно, у проспекта"


cards = []
for n, rv in enumerate(reviews, 1):
    r = ranked[rv["cianId"]]
    o = offers[rv["cianId"]]
    img = base64.b64encode(open(f"{ROOT}/data/photos/{rv['cianId']}.jpg", "rb").read()).decode()
    addr = html.escape(r["address"].split(", м. ")[-1])
    mat = MATERIAL.get(r["materialType"], "материал не указан")
    year = f", {r['buildYear']}" if r["buildYear"] else ""
    fix = "".join(f"<li>{html.escape(f)}</li>" for f in rv["fixable"]) or "<li>нечего</li>"
    owner = "собственник" if "owner" in r["flags"] else "агент"
    deposit = o.get("bargainTerms", {}).get("deposit") or 0
    cards.append(f'''<article class="flat" id="flat-{n}">
<header><span class="num">{n}</span><div class="head"><h2>м. {html.escape(r["metro"])} · {r["metro_walk"]} мин пешком</h2><p class="addr">{addr}</p></div><span class="pill {VERDICT[rv["verdict"]]}">{rv["verdict"]}</span></header>
<dl class="facts"><div><dt>Цена</dt><dd>{money(r["price"])} ₽</dd></div><div><dt>Площадь</dt><dd>{r["totalArea"]} м²</dd></div><div><dt>Этаж</dt><dd>{r["floorNumber"]} из {r["floorsCount"]}</dd></div><div><dt>Дом</dt><dd>{mat}{year}</dd></div><div><dt>Въезд</dt><dd>{money(r["move_in_cost"])} ₽</dd></div><div><dt>Сдаёт</dt><dd>{owner}</dd></div></dl>
<img class="sheet" src="data:image/jpeg;base64,{img}" alt="Фото квартиры {n}">
<div class="cols"><section><h3>Ремонт по фото</h3><div class="scores"><span>база <b>{rv["base"]}</b></span><span>мебель и мелочи <b>{rv["soft"]}</b></span><span class="pred">моя оценка за вас <b>{rv["pred"]}</b></span></div><p>{html.escape(rv["summary"])}</p><p class="sub">Можно убрать или заменить:</p><ul>{fix}</ul></section>
<section><h3>Место</h3><ul class="plain"><li>Парк от 10 га: <b>{r["park_walk"]:.0f} мин</b> пешком</li><li>Музеев и галерей в 25 мин: <b>{r["culture25"]}</b></li><li>Половина мест работы по её профилю: <b>до {r["job_p50"]:.0f} мин</b></li><li>Шум: <b>{quiet_label(r["components"]["quiet"])}</b></li><li>Оценка без ремонта: <b>{r["total"]:.2f}</b> из 1</li></ul><a href="{o["fullUrl"].split("?")[0]}" target="_blank" rel="noopener">Открыть на ЦИАН ↗</a> · залог {money(deposit)} ₽</section></div>
<div class="fb" role="group" aria-label="Ваше мнение о квартире {n}"><button type="button" data-n="{n}" data-v="ok">Согласен</button><button type="button" data-n="{n}" data-v="up">Ремонт лучше, чем я думаю</button><button type="button" data-n="{n}" data-v="down">Ремонт хуже</button></div>
<input id="note-{n}" class="note" placeholder="Комментарий (необязательно)">
</article>''')
tpl = open(f"{ROOT}/src/align_template.html", encoding="utf-8").read()
open(f"{ROOT}/report/align.html", "w", encoding="utf-8").write(tpl.replace("{{CARDS}}", "\n".join(cards)).replace("{{N}}", str(len(reviews))))

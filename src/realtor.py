import json
import re
from datetime import datetime
import numpy as np

ROOT = "D:/Users/Ruslan/VsCodeProjects/moscow-flat"
DESC_RULES = [
    (r"прода[её]тся|продаю|в продаже|продажа квартиры", "minus", "Квартира, похоже, одновременно продаётся: будут показы покупателям, а новый владелец может попросить съехать. Прописать в договоре уведомление за 60 дней."),
    (r"наличн", "check", "Оплата наличными: настаивать на письменном договоре и расписке за каждый платёж."),
    (r"вещи (хозя|собственн)|кладовк[аеу] (закрыт|с вещ)|комната закрыт|хран(ятся|им) вещи", "minus", "Часть квартиры занята вещами собственника. Уточнить, что именно остаётся и где."),
    (r"собственник (будет )?(приходит|навещ|провер)|раз в месяц (приход|провер)|ежемесячн\w* (визит|осмотр|провер)", "check", "Собственник собирается регулярно приходить. Договориться о визитах только по согласованию."),
    (r"за (2|3|два|три) месяца впер[её]д|первый и последний месяц|предоплат", "minus", "Просят оплату за несколько месяцев вперёд: сумма на въезд выше, можно торговаться."),
    (r"без регистрации|регистраци\w* (не|нет)", "check", "Регистрацию не дают. Если она нужна, решить заранее."),
    (r"до (лета|весны|осени|зимы|мая|июня|июля|августа|сентября)|на (полгода|6 месяцев|несколько месяцев)", "minus", "Срок аренды ограничен. Уточнить, можно ли продлить."),
    (r"газов\w* колонк|колонка", "check", "Горячая вода от газовой колонки: проверить, что она исправна."),
    (r"интернет\w* (оплачивается )?отдельно|интернета нет|без интернета", "check", "Интернет не включён или его нет: подключение займёт несколько дней."),
    (r"косметическ\w* ремонт|требует ремонт|без ремонта", "minus", "В описании упомянут косметический ремонт или его отсутствие."),
    (r"мебель (можно )?(вывез|убрать|по договор|по согласован)|можно без мебели|частично меблир", "plus", "Собственник готов убрать или поменять мебель."),
    (r"окна (выходят )?во двор|тих\w* двор|окна в тихий", "plus", "Окна во двор."),
    (r"окна (выходят )?на (проспект|шоссе|дорогу|улицу)", "minus", "Окна на улицу или проспект: послушать шум при закрытых окнах."),
    (r"кондиционер|сплит", "plus", "Есть кондиционер."),
    (r"посудомо", "plus", "Есть посудомоечная машина."),
]
KHRUSH = range(1957, 1969)


def haversine_m(lat, lng, lats, lngs):
    p1, p2 = np.radians(lat), np.radians(lats)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lngs - lng) / 2) ** 2
    return 6371000 * 2 * np.arcsin(np.sqrt(a))


def load_extra():
    pts = json.load(open(f"{ROOT}/data/osm/extra.json", encoding="utf-8"))
    return {k: (np.array([p["lat"] for p in pts if p["kind"] == k]), np.array([p["lng"] for p in pts if p["kind"] == k])) for k in ("construction", "night", "fire")}


def nearest(extra, kind, lat, lng):
    lats, lngs = extra[kind]
    return float(haversine_m(lat, lng, lats, lngs).min()) if len(lats) else 1e9


def money(v):
    return f"{int(v):,}".replace(",", " ")


def days_listed(offer, today):
    created = offer.get("creationDate")
    return (today - datetime.fromisoformat(created[:19])).days if created else None


def inspect(offer, r, review, extra, today):
    minus, check, plus, bargain = [], [], [], []
    price = r["price"]
    floor, floors = r["floorNumber"], r["floorsCount"] or 0
    year = r.get("buildYear")
    bt = offer["bargainTerms"]
    desc = (offer.get("description") or "").lower()
    for pattern, level, text in DESC_RULES:
        if re.search(pattern, desc):
            {"minus": minus, "check": check, "plus": plus}[level].append(text)
    if year in KHRUSH and floors <= 5 and r.get("materialType") in ("panel", "block", "brick", None):
        minus.append(f"Пятиэтажка {year} года: дом может быть в программе реновации. Проверить адрес на mos.ru: при сносе придётся съехать, а стройки рядом идут годами.")
    d = nearest(extra, "construction", r["lat"], r["lng"])
    if d < 300:
        minus.append(f"Стройка в {d:.0f} м по данным OSM: шум с утра и пыль. Проверить на месте, идёт ли она ещё.")
    d = nearest(extra, "night", r["lat"], r["lng"])
    if d < 60:
        minus.append(f"Бар или клуб в {d:.0f} м: может быть шумно ночью по выходным.")
    d = nearest(extra, "fire", r["lat"], r["lng"])
    if d < 250:
        check.append(f"Пожарная часть в {d:.0f} м: сирены в любое время.")
    if floors and floor == floors:
        minus.append("Последний этаж: проверить потолок на следы протечек, летом под крышей жарко.")
    if floor == 2:
        check.append("Второй этаж: узнать, что на первом. Магазин или кафе внизу означает запахи и гул вентиляции.")
    rail = r["noise"]["rail_dist"]
    if rail < 200:
        minus.append(f"Железная дорога или МЦД в {rail:.0f} м: поезда слышно, особенно ночью.")
    if min(r["noise"]["primary_dist"], r["noise"]["noise_dist"]) < 45:
        minus.append("Дом стоит у оживлённой дороги: важно, куда выходят окна спальни.")
    kitchen = float(offer.get("kitchenArea") or 0)
    if 0 < kitchen < 7:
        minus.append(f"Кухня {kitchen:g} м²: вдвоём тесно, стол на двоих встанет с трудом.")
    if not offer.get("balconiesCount") and not offer.get("loggiasCount"):
        check.append("Ни балкона, ни лоджии: бельё сушить в комнате.")
    fee = bt.get("clientFee") or 0
    if fee:
        (minus if fee >= 100 else check).append(f"Комиссия агенту {fee}%: {money(price * fee / 100)} ₽.")
        bargain.append(f"Комиссию {fee}% часто снижают до 50% или делят с собственником." if fee > 50 else f"Комиссию {fee}% иногда удаётся разделить с собственником.")
    deposit = bt.get("deposit") or 0
    if deposit > price:
        minus.append(f"Залог больше месячной платы: {money(deposit)} ₽.")
    if deposit >= price:
        bargain.append("Попросить разбить залог на 2–3 платежа.")
    ut = bt.get("utilitiesTerms") or {}
    if not ut.get("includedInPrice"):
        check.append("Коммунальные платежи сверху: в однушке это ещё примерно 5–9 тыс. ₽ в месяц.")
    elif ut.get("flowMetersNotIncludedInPrice"):
        check.append("Счётчики (вода, свет) оплачиваются отдельно: обычно 1,5–3 тыс. ₽ в месяц.")
    user = offer.get("user") or {}
    if "собственник" in desc and user.get("isAgent") and not offer.get("isByHomeowner"):
        check.append("В тексте «собственник», но размещает агент. Спросить про комиссию до просмотра.")
    days = days_listed(offer, today)
    levers = 0
    if days is not None and days >= 90:
        check.append(f"Объявлению {days} дн. Такие «вечные» объявления часто держат агентства: квартиру могли уже сдать, звонить и уточнять сразу.")
    if days is not None and days >= 14:
        levers += 1
        bargain.append(f"Объявление висит {days} дн. Каждый пустой месяц стоит собственнику всей аренды; это главный аргумент для скидки.")
    ratio = r.get("price_ratio")
    if ratio and ratio >= 1.05:
        levers += 1
        bargain.append(f"Метр здесь на {round((ratio - 1) * 100)}% дороже, чем в похожих квартирах рядом.")
    fixable = (review or {}).get("fixable") or []
    if fixable:
        bargain.append("Попросить вывезти или заменить: " + ", ".join(fixable[:3]) + ".")
    if review and (review.get("bathroom_ok") is False or review.get("kitchen_ok") is False):
        levers += 1
        bargain.append("Санузел или кухня на фото уставшие: аргумент для скидки.")
    if (floors and floor == floors) or 0 < kitchen < 7:
        levers += 1
        bargain.append("Последний этаж или маленькая кухня снижают спрос на квартиру.")
    bargain.append("Сильная позиция арендатора: договор на 11 месяцев, въезд сразу, стабильный доход, без детей и животных.")
    target = int(round(price * (0.94 if levers >= 3 else 0.96 if levers == 2 else 0.97 if levers == 1 else 0.99) / 500) * 500)
    return {"minus": minus, "check": check, "plus": plus, "bargain": bargain, "days_listed": days, "target_price": target}

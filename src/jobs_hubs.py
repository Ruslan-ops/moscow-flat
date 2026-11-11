import json
import time
import requests

HUBS = [
    ("Флакон", "design cluster", ["Флакон, Большая Новодмитровская 36, Москва", "Дизайн-завод Флакон Москва"], 0.9),
    ("Арма", "creative cluster", ["Арма, Нижняя Сыромятническая 10, Москва", "ARMA creative space Moscow"], 0.8),
    ("Винзавод", "art cluster", ["Винзавод, 4-й Сыромятнический переулок 1/8, Москва", "Винзавод Москва"], 0.9),
    ("Хлебозавод №9", "creative cluster", ["Хлебозавод №9, Новоалексеевская 16, Москва", "Хлебозавод 9 Москва"], 0.7),
    ("Даниловская мануфактура", "creative cluster", ["Даниловская мануфактура, Варшавское шоссе 9, Москва", "Даниловская мануфактура"], 0.8),
    ("Красный Октябрь", "creative cluster", ["Красный Октябрь, Берсеневская набережная, Москва", "Красный Октябрь Москва"], 1.0),
    ("Artplay", "design cluster", ["Артплей, Нижняя Сыромятническая 10, Москва", "Artplay Moscow"], 1.0),
    ("Рижский рынок цветы", "flower market", ["Рижский рынок, проспект Мира 94, Москва", "Рижский рынок Москва"], 0.8),
    ("Флорэкспо", "flower wholesale", ["Флорэкспо Москва", "Флора Экспо Москва цветы оптом"], 0.8),
    ("Цветочная база Тепличный", "flower wholesale", ["Тепличный цветочная база Москва", "Цветочный рынок Садовод, Москва"], 0.8),
    ("Москва-Сити", "archviz offices", ["Москва-Сити, Пресненская набережная, Москва", "ММДЦ Москва-Сити"], 0.9),
    ("ЦВЗ Манеж", "exhibition", ["Центральный выставочный зал Манеж, Москва", "Манеж, Манежная площадь, Москва"], 0.6),
    ("ВДНХ", "exhibition", ["ВДНХ, проспект Мира 119, Москва", "ВДНХ Москва"], 0.9),
]

session = requests.Session()
session.headers.update({"User-Agent": "flat-research/1.0"})
out = []
for name, kind, queries, weight in HUBS:
    found = None
    for q in queries:
        time.sleep(1.1)
        r = session.get("https://nominatim.openstreetmap.org/search", params={"format": "json", "q": q, "viewbox": "37.3,55.95,37.95,55.5", "bounded": 1, "limit": 1})
        print(r.status_code)
        if r.status_code != 200:
            time.sleep(5)
            continue
        data = r.json()
        print(name, q, data[0]["display_name"][:80] if data else None)
        if data:
            found = data[0]
            break
    if found:
        out.append({"name": name, "type": kind, "lat": round(float(found["lat"]), 5), "lng": round(float(found["lon"]), 5), "weight": weight})

with open("data/jobs/creative_hubs.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print(len(out))

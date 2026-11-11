import base64
import html
import json
import os
import re
import sys
import numpy as np
from shapely.geometry import shape, box

ROOT = "D:/Users/Ruslan/VsCodeProjects/moscow-flat"
sys.path.insert(0, f"{ROOT}/src")
os.chdir(ROOT)
from transit import door_to_door

LAT0, LON0, LAT1, LON1 = 55.55, 37.35, 55.92, 37.86
MAP_W = 1000
MAP_H = round(MAP_W * (LAT1 - LAT0) / ((LON1 - LON0) * np.cos(np.radians(55.75))))
DATE = "12.11.2026"
HUBS = [("Винзавод, Artplay", ["Винзавод", "Artplay"]), ("Флакон", ["Флакон"]), ("Красный Октябрь", ["Красный Октябрь"]), ("Рижский рынок", ["Рижский рынок цветы"]), ("ВДНХ", ["ВДНХ"])]
MATERIAL = {"brick": "кирпич", "stalin": "сталинский", "monolithBrick": "монолит-кирпич", "monolith": "монолит", "block": "блочный", "panel": "панель", "wood": "дерево"}
VERDICT = {"смотреть": "good", "запасной": "mid", "под вопросом": "mid", "нет": "bad"}
CATEGORY = {"decor": "декор", "archviz": "архвизуализация", "florist_studio": "флористика"}
TIER = {"A": "до 62 000", "B": "62–70 тыс."}


def load(path):
    return json.load(open(f"{ROOT}/{path}", encoding="utf-8"))


def money(v):
    return f"{int(v):,}".replace(",", " ")


def num(v):
    return f"{v:g}".replace(".", ",")


def quiet_label(q):
    return "тихо" if q >= 0.95 else "умеренно" if q >= 0.6 else "шумно, у проспекта"


def esc(t):
    return html.escape(str(t))


def enrich(flats):
    hubs = {h["name"]: (h["lat"], h["lng"]) for h in load("data/jobs/creative_hubs.json")}
    orgs = [o for o in load("data/jobs/dgis_orgs.json") if not o.get("retail_flowers")]
    need = [f for f in flats if not f.get("commute") or not f.get("nearby_jobs")]
    if not need:
        return
    origins = [[f["lat"], f["lng"]] for f in need]
    hub_t = np.column_stack([np.min([door_to_door(origins, [hubs[n]])[:, 0] for n in names], axis=0) for _, names in HUBS])
    org_t = door_to_door(origins, [[o["lat"], o["lng"]] for o in orgs])
    for i, f in enumerate(need):
        f["commute"] = {label: int(round(hub_t[i, j])) for j, (label, _) in enumerate(HUBS)}
        jobs = []
        seen = set()
        for k in np.argsort(org_t[i]):
            name = orgs[k]["name"].split(",")[0].strip()
            if name.lower() in seen:
                continue
            seen.add(name.lower())
            jobs.append({"name": name, "category": orgs[k]["category"], "minutes": int(round(org_t[i, k]))})
            if len(jobs) == 3:
                break
        f["nearby_jobs"] = jobs


def inline(t):
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(t))


def md_sections(path):
    out = []
    items = []
    body = []
    state = {"kind": None, "title": None}

    def flush_list():
        if items:
            tag = "ol" if state["kind"] == "ol" else "ul"
            body.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
            items.clear()

    def flush_section():
        flush_list()
        if state["title"]:
            out.append(f'<section class="text"><h3>{esc(state["title"])}</h3>{"".join(body)}</section>')
        body.clear()

    for line in open(f"{ROOT}/{path}", encoding="utf-8").read().splitlines():
        line = line.rstrip()
        if line.startswith("## "):
            flush_section()
            state["title"] = line[3:].strip()
        elif re.match(r"^\d+\.\s", line):
            if state["kind"] != "ol":
                flush_list()
            state["kind"] = "ol"
            items.append(re.sub(r"^\d+\.\s+", "", line))
        elif line.startswith("- "):
            if state["kind"] != "ul":
                flush_list()
            state["kind"] = "ul"
            items.append(line[2:])
        elif line.strip() and not line.startswith("#") and state["title"]:
            flush_list()
            body.append(f"<p>{inline(line)}</p>")
        elif not line.strip():
            flush_list()
    flush_section()
    return "".join(out)


def metro_runs(line):
    pts = [(s["lat"], s["lng"]) for s in sorted(line["stations"], key=lambda s: s["order"])]
    if line["id"] in ("5", "95"):
        pts.append(pts[0])
    runs = []
    run = []
    for p in pts + [None]:
        if p is not None and LAT0 <= p[0] <= LAT1 and LON0 <= p[1] <= LON1:
            run.append([round(p[0], 5), round(p[1], 5)])
            continue
        if len(run) > 1:
            runs.append({"c": f"#{line['hex_color']}", "p": run})
        run = []
    return runs


def map_data(flats):
    heat = load("data/layers/heat.json")
    vals = np.array(heat["values"], dtype=float)
    lo, hi = np.quantile(vals[vals > 0], [0.05, 0.98])
    scaled = np.where(vals > 0, np.clip(np.round((vals - lo) / (hi - lo) * 99) + 1, 1, 100), 0).astype(int)
    clip = box(LON0, LAT0, LON1, LAT1)
    parks = []
    for ft in load("data/osm/green.json")["features"]:
        if ft["properties"]["area_ha"] < 15:
            continue
        g = shape(ft["geometry"]).buffer(0).intersection(clip).simplify(0.0004)
        for p in getattr(g, "geoms", [g]):
            if p.geom_type == "Polygon" and not p.is_empty:
                parks.append([[round(x, 4), round(y, 4)] for x, y in p.exterior.coords])
    lines = [r for ln in load("data/metro/hh_metro.json")["lines"] for r in metro_runs(ln)]
    hub_xy = {h["name"]: (h["lat"], h["lng"]) for h in load("data/jobs/creative_hubs.json")}
    marks = [{"n": label, "lat": float(np.mean([hub_xy[n][0] for n in names])), "lng": float(np.mean([hub_xy[n][1] for n in names]))} for label, names in HUBS]
    pins = [{"r": f["rank"], "t": f["tier"], "lat": f["lat"], "lng": f["lng"], "p": f["price"], "m": f["metro"]} for f in flats]
    heat_out = {"lat0": heat["lat0"], "lon0": heat["lon0"], "dlat": heat["dlat"], "dlon": heat["dlon"], "v": scaled.tolist()}
    return {"w": MAP_W, "h": MAP_H, "bbox": [LAT0, LON0, LAT1, LON1], "heat": heat_out, "parks": parks, "lines": lines, "marks": marks, "pins": pins}


def card(f):
    rv = f["review"]
    pl = f["place"]
    n = f["rank"]
    photo = f"{ROOT}/data/photos/{f['cianId']}.jpg"
    img = f'<img class="sheet" src="data:image/jpeg;base64,{base64.b64encode(open(photo, "rb").read()).decode()}" alt="Фото квартиры {n}">' if os.path.exists(photo) else ""
    year = f", {f['buildYear']}" if f["buildYear"] else ""
    fix = "".join(f"<li>{esc(x)}</li>" for x in rv.get("fixable") or []) or "<li>нечего</li>"
    flags = "".join(f"<li>{esc(x)}</li>" for x in rv.get("red_flags") or [])
    flags_html = f'<p class="sub">На что обратить внимание:</p><ul class="warn">{flags}</ul>' if flags else ""
    kitchen = f'<div><dt>Кухня</dt><dd>{num(f["kitchen"])} м²</dd></div>' if f.get("kitchen") else ""
    hubs = "".join(f'<li class="hub{" fast" if m <= 30 else ""}"><span class="hn">{esc(name)}</span><span class="trk"><i style="width:{min(100, round(m / 60 * 100))}%"></i></span><b>{m} мин</b></li>' for name, m in f["commute"].items())
    jobs = "".join(f'<li><span>{esc(j["name"])}<span class="sub"> · {CATEGORY.get(j["category"], esc(j["category"]))}</span></span><b>{j["minutes"]} мин</b></li>' for j in f["nearby_jobs"])
    avito = f' · <a href="{esc(f["avito_url"])}" target="_blank" rel="noopener">Авито ↗</a>' if f.get("avito_url") else ""
    return f'''<article class="flat" id="flat-{n}" tabindex="-1" data-rank="{n}" data-tier="{f["tier"]}" data-verdict="{esc(rv["verdict"])}" data-price="{f["price"]}">
<header><span class="num">{n}</span><div class="head"><h3 class="ct">м. {esc(f["metro"])} · {f["metro_walk"]} мин пешком</h3><p class="addr">{esc(f["address"].split(", м. ")[-1])}</p></div><div class="tags"><span class="tier">{TIER.get(f["tier"], esc(f["tier"]))}</span><span class="pill {VERDICT.get(rv["verdict"], "mid")}">{esc(rv["verdict"])}</span></div></header>
<dl class="facts"><div><dt>Цена</dt><dd>{money(f["price"])} ₽</dd></div><div><dt>Площадь</dt><dd>{num(f["totalArea"])} м²</dd></div>{kitchen}<div><dt>Этаж</dt><dd>{f["floorNumber"]} из {f["floorsCount"]}</dd></div><div><dt>Дом</dt><dd>{MATERIAL.get(f["materialType"], "материал не указан")}{year}</dd></div><div><dt>Въезд</dt><dd>{money(f["move_in_cost"])} ₽</dd></div><div><dt>Сдаёт</dt><dd>{"собственник" if f["owner"] else "агент"}</dd></div></dl>
{img}
<div class="cols"><section><h4>Ремонт по фото</h4><div class="scores"><span>база <b>{rv["base"]}</b></span><span>мебель и мелочи <b>{rv["soft"]}</b></span><span class="pred">итог <b>{rv["pred"]}</b></span></div><p>{esc(rv["summary"])}</p><p class="sub">Можно убрать или заменить:</p><ul>{fix}</ul>{flags_html}</section>
<section><h4>Место</h4><ul class="plain"><li>Парк от 10 га: <b>{pl["park_walk"]:.0f} мин</b> пешком</li><li>Музеев и галерей в 25 мин: <b>{pl["culture25"]}</b></li><li>Половина студий по её профилю: <b>до {pl["job_p50"]:.0f} мин</b></li><li>Шум: <b>{quiet_label(pl["quiet"])}</b></li></ul></section></div>
<div class="cols even"><section><h4>Дорога от дома</h4><ul class="hubs">{hubs}</ul><p class="sub">Метро и пешком, дверь в дверь. Зелёным отмечено то, что быстрее 30 минут.</p></section>
<section><h4>Рядом работа</h4><ul class="jobs">{jobs}</ul></section></div>
<p class="links"><a href="{esc(f["url"])}" target="_blank" rel="noopener">ЦИАН ↗</a>{avito} · залог {money(f["deposit"])} ₽</p>
</article>'''


def main():
    flats = load("data/report/finalists.json")
    enrich(flats)
    flats.sort(key=lambda f: f.get("rank") or 10**6)
    for i, f in enumerate(flats, 1):
        f["rank"] = i
    n_a = sum(f["tier"] == "A" for f in flats)
    data = json.dumps(map_data(flats), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    tpl = open(f"{ROOT}/src/report_template.html", encoding="utf-8").read()
    out = tpl.replace("{{CARDS}}", "\n".join(card(f) for f in flats)).replace("{{SECTIONS}}", md_sections("docs/report_text.md")).replace("{{MAPDATA}}", data).replace("{{ASPECT}}", f"{MAP_W} / {MAP_H}").replace("{{N}}", str(len(flats))).replace("{{NA}}", str(n_a)).replace("{{NB}}", str(len(flats) - n_a)).replace("{{DATE}}", DATE)
    os.makedirs(f"{ROOT}/report", exist_ok=True)
    open(f"{ROOT}/report/index.html", "w", encoding="utf-8").write(out)
    print(len(out.encode("utf-8")), "bytes", len(data), "map bytes")


main()

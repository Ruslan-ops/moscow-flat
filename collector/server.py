import argparse
import csv
import json
import os
import random
import re
import sqlite3
import statistics
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))).replace("\\", "/")
HOST = "127.0.0.1"
PORT = 8765
DATA_DIR = f"{ROOT}/data/avito"
DB_PATH = f"{DATA_DIR}/collector.sqlite"
SAMPLES_DIR = f"{DATA_DIR}/samples"
FAILED_DIR = f"{DATA_DIR}/failed"
RATE_LOG_PATH = f"{DATA_DIR}/rate_log.csv"
SAMPLES_PER_KIND = 3

SEARCH_BASE = "https://www.avito.ru/moskva/kvartiry/sdam/na_dlitelnyy_srok-ASgBAgICAkSSA8gQ8AeQUg"
SEARCH_PARAMS = {"pmax": 70000, "s": 104}
DEFAULT_PAGES = 60
AVITO_ORIGIN = "https://www.avito.ru"

START_INTERVAL_MS = 38_000
MIN_INTERVAL_MS = 12_000
MAX_INTERVAL_MS = 180_000
SUCCESS_DECAY = 0.8
SUCCESSES_PER_DECAY = 5
BLOCK_GROWTH = 2.0
JITTER = 0.25
LONG_PAUSE_MIN_TASKS = 25
LONG_PAUSE_MAX_TASKS = 40
LONG_PAUSE_MIN_S = 30
LONG_PAUSE_MAX_S = 90
BLOCK_PAUSE_S = 180
BLOCK_WINDOW_S = 30 * 60
BLOCK_LIMIT_IN_WINDOW = 3
MAX_ATTEMPTS = 3
DEFAULT_HARD_CAP = 1000

WALK_RE = r"(?:до\s*(\d+)|(\d+)\s*[–—-]\s*(\d+)|(?:более|свыше)\s*(\d+))\s*мин"
METRO_RE = re.compile(rf"(?:м\.\s*)?([А-ЯЁA-Z][^\d,;|]*?)\s*{WALK_RE}")
ROOMS_RE = re.compile(r"(\d+)\s*-?\s*к(?:омн)?\b")
AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*м[²2]")
FLOOR_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s*эт")
SPACES_RE = re.compile(r"[\s  ]+")


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def clean(text):
    return SPACES_RE.sub(" ", text or "").strip()


def parse_title(title):
    t = clean(title)
    low = t.lower()
    rooms_m = ROOMS_RE.search(low)
    studio = "студи" in low
    area_m = AREA_RE.search(t)
    floor_m = FLOOR_RE.search(low)
    return {
        "rooms": int(rooms_m.group(1)) if rooms_m else (0 if studio else None),
        "studio": studio,
        "area": float(area_m.group(1).replace(",", ".")) if area_m else None,
        "floor": int(floor_m.group(1)) if floor_m else None,
        "floors": int(floor_m.group(2)) if floor_m else None,
        "apartments": "апартамент" in low,
    }


def parse_metro(text):
    stations = []
    for m in METRO_RE.finditer(clean(text)):
        station = m.group(1).strip()
        if m.group(2):
            lo, hi = 0, int(m.group(2))
        elif m.group(3):
            lo, hi = int(m.group(3)), int(m.group(4))
        else:
            lo, hi = int(m.group(5)), None
        stations.append({"station": station, "walk_min_from": lo, "walk_min_to": hi})
    return stations


def parse_seller(badges, text):
    blob = " ".join(badges or []) + " " + (text or "")
    seller_type = "agency" if "Агентство" in blob else "owner" if "Собственник" in blob else "unknown"
    return seller_type, "Без комиссии" in blob


def enrich_card(hit):
    card = dict(hit)
    card.update(parse_title(card.get("title")))
    stations = parse_metro(card.get("metro_text") or card.get("location"))
    card["metro"] = stations
    card["metro_station"] = stations[0]["station"] if stations else None
    card["metro_walk_from"] = stations[0]["walk_min_from"] if stations else None
    card["metro_walk_to"] = stations[0]["walk_min_to"] if stations else None
    card["seller_type"], card["no_commission"] = parse_seller(card.get("badges"), card.get("text"))
    return card


def strip_context(url):
    if not url:
        return url
    parsed = urlparse(url)
    if not parsed.query:
        return url
    qs = parse_qs(parsed.query, keep_blank_values=True)
    qs.pop("context", None)
    return parsed._replace(query="&".join(f"{k}={v[0]}" for k, v in qs.items())).geturl().rstrip("?")


def build_search_url(page):
    params = "&".join(f"{k}={v}" for k, v in {**SEARCH_PARAMS, "p": page}.items())
    return f"{SEARCH_BASE}?{params}"


def normalize_url(url):
    url = url.strip()
    return strip_context(f"{AVITO_ORIGIN}{url}" if url.startswith("/") else url)


def read_lines(path):
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip() and not line.strip().startswith("#")]


def median(values):
    values = [v for v in values if v is not None]
    return int(statistics.median(values)) if values else None


class PacingState:
    PERSISTED_FIELDS = ("interval_ms", "last_safe_interval", "consecutive_successes", "session_pages", "last_navigation_start")

    def __init__(self, hard_cap=DEFAULT_HARD_CAP):
        self.interval_ms = START_INTERVAL_MS
        self.last_safe_interval = START_INTERVAL_MS
        self.consecutive_successes = 0
        self.block_timestamps = []
        self.session_pages = 0
        self.hard_cap = hard_cap
        self.tasks_until_long_pause = random.randint(LONG_PAUSE_MIN_TASKS, LONG_PAUSE_MAX_TASKS)
        self.paused = False
        self.pause_reason = None
        self.paused_until = None
        self.last_navigation_start = None
        self.last_actual_interval_ms = None

    def to_persisted_dict(self):
        return {k: getattr(self, k) for k in self.PERSISTED_FIELDS}

    def load_persisted_dict(self, d):
        for k in self.PERSISTED_FIELDS:
            if d.get(k) is not None:
                setattr(self, k, d[k])
        self.last_safe_interval = max(self.last_safe_interval, MIN_INTERVAL_MS)
        self.interval_ms = min(max(self.interval_ms, MIN_INTERVAL_MS), MAX_INTERVAL_MS)

    def record_success(self):
        self.consecutive_successes += 1
        if self.consecutive_successes % SUCCESSES_PER_DECAY == 0:
            self.interval_ms = max(MIN_INTERVAL_MS, int(self.interval_ms * SUCCESS_DECAY))

    def record_block(self):
        now = time.time()
        self.consecutive_successes = 0
        self.last_safe_interval = self.interval_ms
        self.interval_ms = min(MAX_INTERVAL_MS, int(self.interval_ms * BLOCK_GROWTH))
        self.block_timestamps = [t for t in self.block_timestamps + [now] if now - t <= BLOCK_WINDOW_S]
        self.paused = True
        if len(self.block_timestamps) >= BLOCK_LIMIT_IN_WINDOW:
            self.pause_reason = f"{len(self.block_timestamps)} blocks within {BLOCK_WINDOW_S // 60} min"
            self.paused_until = None
        else:
            self.pause_reason = "block cooldown"
            self.paused_until = now + BLOCK_PAUSE_S

    def manual_pause(self, reason="manual"):
        self.paused = True
        self.pause_reason = reason
        self.paused_until = None

    def manual_resume(self):
        self.paused = False
        self.pause_reason = None
        self.paused_until = None

    def note_dispatch(self):
        self.session_pages += 1
        self.tasks_until_long_pause -= 1

    def is_paused(self):
        if not self.paused:
            return False
        if self.paused_until is not None and time.time() >= self.paused_until:
            self.manual_resume()
            return False
        return True

    def session_cap_reached(self):
        return self.session_pages >= self.hard_cap

    def next_delay_ms(self):
        jittered = max(MIN_INTERVAL_MS * 0.5, self.interval_ms * (1 + random.uniform(-JITTER, JITTER)))
        long_pause_ms = 0
        if self.tasks_until_long_pause <= 0:
            long_pause_ms = random.randint(LONG_PAUSE_MIN_S, LONG_PAUSE_MAX_S) * 1000
            self.tasks_until_long_pause = random.randint(LONG_PAUSE_MIN_TASKS, LONG_PAUSE_MAX_TASKS)
        target_interval_ms = int(jittered) + long_pause_ms
        now = time.time()
        if self.last_navigation_start is None:
            delay_ms = target_interval_ms
            self.last_actual_interval_ms = None
        else:
            elapsed_ms = (now - self.last_navigation_start) * 1000.0
            delay_ms = max(0, int(target_interval_ms - elapsed_ms))
            self.last_actual_interval_ms = int(elapsed_ms + delay_ms)
        self.last_navigation_start = now + delay_ms / 1000.0
        return delay_ms

    def status(self):
        return {
            "delay_ms": self.interval_ms,
            "interval_ms": self.interval_ms,
            "last_safe_interval": self.last_safe_interval,
            "consecutive_successes": self.consecutive_successes,
            "blocks_recent": len([t for t in self.block_timestamps if time.time() - t <= BLOCK_WINDOW_S]),
            "blocks_total": len(self.block_timestamps),
            "session_pages": self.session_pages,
            "hard_cap": self.hard_cap,
            "paused": self.is_paused(),
            "pause_reason": self.pause_reason,
            "paused_until": self.paused_until,
        }


class Collector:
    PACING_KV_KEY = "pacing_state"

    def __init__(self, db_path=DB_PATH, hard_cap=DEFAULT_HARD_CAP):
        self.db_path = db_path
        self.lock = threading.RLock()
        self.pacing = PacingState(hard_cap=hard_cap)
        self.issued = {}
        self.recent_intervals = deque(maxlen=20)
        self.recent_ready_ms = deque(maxlen=20)
        for d in (os.path.dirname(db_path), SAMPLES_DIR, FAILED_DIR):
            os.makedirs(d, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.init_db()
        self.load_pacing()

    def init_db(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0,
                meta TEXT,
                created TEXT NOT NULL,
                updated TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS search_cards (
                item_id TEXT PRIMARY KEY,
                json TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS items (
                item_id TEXT PRIMARY KEY,
                json TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                type TEXT NOT NULL,
                detail TEXT
            );
            CREATE TABLE IF NOT EXISTS kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def load_pacing(self):
        row = self.conn.execute("SELECT value FROM kv WHERE key = ?", (self.PACING_KV_KEY,)).fetchone()
        if row is not None:
            self.pacing.load_persisted_dict(json.loads(row["value"]))

    def save_pacing(self):
        self.conn.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (self.PACING_KV_KEY, json.dumps(self.pacing.to_persisted_dict())),
        )
        self.conn.commit()

    def log_event(self, type_, detail=None):
        detail = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)
        self.conn.execute("INSERT INTO events (ts, type, detail) VALUES (?, ?, ?)", (now_iso(), type_, detail))
        self.conn.commit()

    def log_rate(self, task_type, delay_used_ms, outcome, interval_actual_ms, timings):
        new_file = not os.path.exists(RATE_LOG_PATH)
        with open(RATE_LOG_PATH, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(["ts", "task_type", "delay_used_ms", "outcome", "interval_actual_ms", "ready_ms", "extract_ms", "total_ms"])
            w.writerow([now_iso(), task_type, delay_used_ms, outcome, interval_actual_ms, timings.get("ready_ms"), timings.get("extract_ms"), timings.get("total_ms")])

    def get_task(self, task_id):
        return self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()

    def set_task_status(self, task_id, status, attempts=None, meta=None):
        row = self.get_task(task_id)
        self.conn.execute(
            "UPDATE tasks SET status = ?, attempts = ?, meta = ?, updated = ? WHERE id = ?",
            (status, row["attempts"] if attempts is None else attempts, row["meta"] if meta is None else meta, now_iso(), task_id),
        )
        self.conn.commit()

    def enqueue_task(self, type_, url, meta=None, force=False):
        with self.lock:
            now = now_iso()
            try:
                cur = self.conn.execute(
                    "INSERT INTO tasks (type, url, status, attempts, meta, created, updated) VALUES (?, ?, 'queued', 0, ?, ?, ?)",
                    (type_, url, json.dumps(meta or {}, ensure_ascii=False), now, now),
                )
                self.conn.commit()
                return cur.lastrowid
            except sqlite3.IntegrityError:
                if not force:
                    return None
                cur = self.conn.execute("UPDATE tasks SET status = 'queued', attempts = 0, updated = ? WHERE url = ? AND status != 'in_progress'", (now, url))
                self.conn.commit()
                return cur.rowcount or None

    def seed_pages(self, pages=DEFAULT_PAGES, force=False):
        return [self.enqueue_task("search", build_search_url(p), {"page": p}, force) for p in range(1, pages + 1)]

    def seed_search_urls(self, urls, force=False):
        return [self.enqueue_task("search", normalize_url(u), {}, force) for u in urls]

    def seed_item_urls(self, urls, force=False):
        return [self.enqueue_task("item", normalize_url(u), {}, force) for u in urls]

    def next_task(self):
        with self.lock:
            if self.pacing.is_paused():
                return {"paused": True, "reason": self.pacing.pause_reason}
            if self.pacing.session_cap_reached():
                return {"paused": True, "reason": "session cap reached"}
            row = self.conn.execute("SELECT * FROM tasks WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
            if row is None:
                return {"idle": True}
            delay_ms = self.pacing.next_delay_ms()
            self.pacing.note_dispatch()
            self.set_task_status(row["id"], "in_progress")
            self.issued[row["id"]] = {"delay": delay_ms, "interval": self.pacing.last_actual_interval_ms, "type": row["type"]}
            self.save_pacing()
            task = {"id": row["id"], "type": row["type"], "url": row["url"], "attempts": row["attempts"], "meta": json.loads(row["meta"] or "{}")}
            return {"task": task, "delay_ms": delay_ms}

    def requeue_or_fail(self, task_row):
        attempts = task_row["attempts"] + 1
        status = "queued" if attempts < MAX_ATTEMPTS else "failed"
        self.set_task_status(task_row["id"], status, attempts=attempts)
        return status

    def save_html(self, directory, name, html):
        if html:
            with open(f"{directory}/{name}.html", "w", encoding="utf-8") as f:
                f.write(html)

    def save_sample(self, kind, name, html):
        existing = [f for f in os.listdir(SAMPLES_DIR) if f.startswith(f"{kind}_")]
        if len(existing) < SAMPLES_PER_KIND:
            self.save_html(SAMPLES_DIR, f"{kind}_{name}", html)

    @staticmethod
    def is_valid_item(data):
        return bool(data) and bool(data.get("title")) and bool(data.get("item_id"))

    def store_item(self, data, html):
        item_id = str(data["item_id"])
        self.save_sample("item", item_id, html)
        self.conn.execute(
            "INSERT INTO items (item_id, json, fetched_at) VALUES (?, ?, ?) ON CONFLICT(item_id) DO UPDATE SET json = excluded.json, fetched_at = excluded.fetched_at",
            (item_id, json.dumps(data, ensure_ascii=False), now_iso()),
        )

    def store_search(self, task_row, data, html):
        now = now_iso()
        page = data.get("page")
        self.save_sample("search", f"p{page}", html)
        stored = 0
        for hit in data.get("hits") or []:
            hit["url"] = strip_context(hit.get("url"))
            if not hit.get("item_id"):
                continue
            card = enrich_card(hit)
            card["page"] = page
            self.conn.execute(
                "INSERT INTO search_cards (item_id, json, first_seen, last_seen) VALUES (?, ?, ?, ?) ON CONFLICT(item_id) DO UPDATE SET json = excluded.json, last_seen = excluded.last_seen",
                (str(card["item_id"]), json.dumps(card, ensure_ascii=False), now, now),
            )
            stored += 1
        meta = json.loads(task_row["meta"] or "{}")
        meta.update({"total_results": data.get("total_results"), "total_pages": data.get("total_pages"), "cards": stored})
        return json.dumps(meta, ensure_ascii=False)

    def submit_result(self, task_id, ok, kind=None, data=None, html=None, reason=None, timings=None):
        with self.lock:
            task_row = self.get_task(task_id)
            issued = self.issued.pop(task_id, {})
            timings = timings or {}
            if issued.get("interval") is not None:
                self.recent_intervals.append(issued["interval"])
            if timings.get("ready_ms") is not None:
                self.recent_ready_ms.append(timings["ready_ms"])
            if task_row is None:
                return {"error": "unknown task_id"}
            outcome = "failed"
            if kind == "gone":
                self.set_task_status(task_id, "gone")
                self.log_event("gone", {"task_id": task_id, "reason": reason})
                outcome = "gone"
            elif ok and kind == "item" and self.is_valid_item(data):
                self.store_item(data, html)
                self.set_task_status(task_id, "done")
                self.pacing.record_success()
                self.save_pacing()
                outcome = "ok"
            elif ok and kind == "search" and data is not None and (data.get("hits") or data.get("page")):
                meta = self.store_search(task_row, data, html)
                self.set_task_status(task_id, "done", meta=meta)
                if not data.get("hits"):
                    self.log_event("empty_search", {"task_id": task_id, "url": task_row["url"]})
                    self.save_html(FAILED_DIR, f"empty_{task_id}", html)
                self.pacing.record_success()
                self.save_pacing()
                outcome = "ok"
            else:
                self.save_html(FAILED_DIR, f"{time.strftime('%Y%m%d%H%M%S')}_{task_id}", html)
                status = self.requeue_or_fail(task_row)
                outcome = "invalid" if ok else "failed"
                self.log_event("result_invalid_or_failed", {"task_id": task_id, "ok": ok, "kind": kind, "status": status})
            self.log_rate(issued.get("type") or task_row["type"], issued.get("delay") or 0, outcome, issued.get("interval"), timings)
            return {"status": "recorded", "outcome": outcome}

    def submit_block(self, task_id, reason=None, timings=None):
        with self.lock:
            task_row = self.get_task(task_id)
            issued = self.issued.pop(task_id, {})
            timings = timings or {}
            if issued.get("interval") is not None:
                self.recent_intervals.append(issued["interval"])
            if timings.get("ready_ms") is not None:
                self.recent_ready_ms.append(timings["ready_ms"])
            self.pacing.record_block()
            self.save_pacing()
            self.log_event("block", {"task_id": task_id, "reason": reason})
            if task_row is not None:
                self.requeue_or_fail(task_row)
            self.log_rate(issued.get("type") or "unknown", issued.get("delay") or 0, "blocked", issued.get("interval"), timings)
            return {"status": "recorded", "paused": self.pacing.paused, "pause_reason": self.pacing.pause_reason, "delay_ms": self.pacing.interval_ms}

    def last_event(self, types=None):
        where = f"WHERE type IN ({','.join('?' * len(types))})" if types else ""
        row = self.conn.execute(f"SELECT ts, type, detail FROM events {where} ORDER BY id DESC LIMIT 1", types or ()).fetchone()
        return {"ts": row["ts"], "type": row["type"], "detail": row["detail"]} if row else None

    def count(self, sql, args=()):
        return self.conn.execute(sql, args).fetchone()[0]

    def status(self):
        with self.lock:
            counts = {row["status"]: row["n"] for row in self.conn.execute("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status")}
            thirty_min_ago = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 30 * 60))
            st = self.pacing.status()
            st["task_counts"] = counts
            st["items_count"] = self.count("SELECT COUNT(*) FROM items")
            st["cards_count"] = self.count("SELECT COUNT(*) FROM search_cards")
            actual = median(self.recent_intervals)
            st["target_interval_ms"] = self.pacing.interval_ms
            st["actual_interval_median_ms"] = actual
            st["ready_ms_median"] = median(self.recent_ready_ms)
            st["ready_ms_last"] = self.recent_ready_ms[-1] if self.recent_ready_ms else None
            st["items_per_hour"] = self.count("SELECT COUNT(*) FROM items WHERE fetched_at >= ?", (thirty_min_ago,)) * 2
            st["counts"] = {
                "done": counts.get("done", 0),
                "queued": counts.get("queued", 0),
                "gone": counts.get("gone", 0),
                "failed": counts.get("failed", 0),
                "deferred": self.count("SELECT COUNT(*) FROM tasks WHERE status = 'queued' AND attempts > 0"),
                "skipped": 0,
            }
            st["eta_minutes"] = round((counts.get("queued", 0) * (actual or self.pacing.interval_ms)) / 60000.0, 1)
            st["last_event"] = self.last_event()
            st["last_error"] = self.last_event(["block", "result_invalid_or_failed"])
            return st

    def pause(self, reason="manual"):
        with self.lock:
            self.pacing.manual_pause(reason)
            self.log_event("pause", reason)
            return self.status()

    def resume(self):
        with self.lock:
            self.pacing.manual_resume()
            self.log_event("resume")
            return self.status()

    def close(self):
        self.conn.close()


class Handler(BaseHTTPRequestHandler):
    collector = None

    def log_message(self, fmt, *args):
        pass

    def cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors_headers()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/next":
            self.send_json(self.collector.next_task())
        elif path == "/status":
            self.send_json(self.collector.status())
        else:
            self.send_json({"error": "not found"}, 404)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def do_POST(self):
        path = urlparse(self.path).path
        body = self.read_body()
        c = self.collector
        if path == "/result":
            self.send_json(c.submit_result(body.get("task_id"), bool(body.get("ok")), body.get("kind"), body.get("data"), body.get("html"), body.get("reason"), body.get("timings")))
        elif path == "/block":
            self.send_json(c.submit_block(body.get("task_id"), body.get("reason"), body.get("timings")))
        elif path == "/pause":
            self.send_json(c.pause(body.get("reason", "manual")))
        elif path == "/resume":
            self.send_json(c.resume())
        else:
            self.send_json({"error": "not found"}, 404)


def serve(hard_cap):
    collector = Collector(hard_cap=hard_cap)
    Handler.collector = collector
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"collector listening on http://{HOST}:{PORT}, db {DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        collector.close()


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--hard-cap", type=int, default=DEFAULT_HARD_CAP)
    p_pages = sub.add_parser("seed-pages")
    p_pages.add_argument("--pages", type=int, default=DEFAULT_PAGES)
    p_pages.add_argument("--force", action="store_true")
    p_searches = sub.add_parser("seed-searches")
    p_searches.add_argument("file")
    p_searches.add_argument("--force", action="store_true")
    p_items = sub.add_parser("seed-items")
    p_items.add_argument("file")
    p_items.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.cmd in (None, "serve"):
        serve(getattr(args, "hard_cap", DEFAULT_HARD_CAP))
        return
    collector = Collector()
    if args.cmd == "seed-pages":
        ids = collector.seed_pages(args.pages, args.force)
    elif args.cmd == "seed-searches":
        ids = collector.seed_search_urls(read_lines(args.file), args.force)
    else:
        ids = collector.seed_item_urls(read_lines(args.file), args.force)
    print(f"enqueued {len([i for i in ids if i])} of {len(ids)}")
    collector.close()


if __name__ == "__main__":
    main()

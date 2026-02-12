"""
AutoRia async scraper — Producer/Consumer + asyncpg + PostgreSQL
================================================================
Run:  python scraper.py
Dump: python scraper.py --dump
"""

import asyncio
import json
import logging
import os
import random
import re
import subprocess
from datetime import datetime, time
from typing import Any, Dict, Optional

import aiohttp
import asyncpg
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("autoria")

# ── Config ──────────────────────────────────────────────────────────────────

START_URL    = os.getenv("START_URL", "https://auto.ria.com/uk/search/?indexName=auto&page=0")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/autoria")
NUM_WORKERS  = int(os.getenv("NUM_WORKERS", "5"))
DUMP_DIR     = os.getenv("DUMP_DIR", "/dumps")
DUMP_TIME    = time(hour=12, minute=0)          # daily pg_dump at 12:00

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "DNT": "1",
}

HEADERS_FF = {
    **HEADERS,
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
        "Gecko/20100101 Firefox/121.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

BROWSER_PROFILES = [HEADERS, HEADERS_FF]

# ── Database ─────────────────────────────────────────────────────────────────

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cars (
    id              SERIAL PRIMARY KEY,
    url             TEXT UNIQUE NOT NULL,
    title           TEXT,
    price_usd       NUMERIC,
    odometer        INTEGER,
    username        TEXT,
    phone_number    TEXT,
    image_url       TEXT,
    images_count    INTEGER,
    car_number      TEXT,
    car_vin         TEXT,
    fuel_type       TEXT,
    transmission    TEXT,
    engine_volume   TEXT,
    drive_type      TEXT,
    datetime_found  TIMESTAMP DEFAULT NOW()
);
"""

UPSERT_SQL = """
INSERT INTO cars (url, title, price_usd, odometer, username, phone_number,
                  image_url, images_count, car_number, car_vin,
                  fuel_type, transmission, engine_volume, drive_type,
                  datetime_found)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
ON CONFLICT (url) DO UPDATE SET
    title          = EXCLUDED.title,
    price_usd      = EXCLUDED.price_usd,
    odometer       = EXCLUDED.odometer,
    username       = EXCLUDED.username,
    phone_number   = COALESCE(EXCLUDED.phone_number, cars.phone_number),
    image_url      = EXCLUDED.image_url,
    images_count   = EXCLUDED.images_count,
    car_number     = EXCLUDED.car_number,
    car_vin        = EXCLUDED.car_vin,
    fuel_type      = EXCLUDED.fuel_type,
    transmission   = EXCLUDED.transmission,
    engine_volume  = EXCLUDED.engine_volume,
    drive_type     = EXCLUDED.drive_type,
    datetime_found = EXCLUDED.datetime_found
RETURNING (xmax = 0) AS is_insert;
"""

async def init_db(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLE_SQL)

async def save_car(pool: asyncpg.Pool, d: Dict) -> bool:
    """Upsert one car. Returns True if it was a new insert."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            UPSERT_SQL,
            d["url"], d["title"], d["price_usd"], d["odometer"],
            d["username"], d["phone_number"], d["image_url"],
            d["images_count"], d["car_number"], d["car_vin"],
            d["fuel_type"], d["transmission"], d["engine_volume"], d["drive_type"],
            d["datetime_found"],
        )
        return row["is_insert"] if row else False

# ── HTTP helpers ─────────────────────────────────────────────────────────────

async def fetch(session: aiohttp.ClientSession, url: str, retries: int = 3) -> Optional[str]:
    """GET with exponential back-off on 429/5xx."""
    delay = 1.0
    for attempt in range(retries):
        await asyncio.sleep(random.uniform(0.2, 0.6))
        try:
            headers = {**random.choice(BROWSER_PROFILES), "Referer": "https://auto.ria.com/"}
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 200:
                    return await r.text()
                if r.status in (429, 500, 502, 503, 504):
                    wait = min(float(r.headers.get("Retry-After", delay)), 60)
                    log.warning("HTTP %d — retry %d in %.1fs", r.status, attempt + 1, wait)
                    await asyncio.sleep(wait)
                    delay *= 2
                    continue
                log.warning("HTTP %d: %s", r.status, url)
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log.warning("Request error attempt %d: %s", attempt + 1, e)
            await asyncio.sleep(delay)
            delay *= 2
    return None

# ── Parsing ───────────────────────────────────────────────────────────────────

def _int(text: str) -> Optional[int]:
    m = re.search(r"\d+", text.replace("\xa0", "").replace(" ", ""))
    return int(m.group()) if m else None

def parse_car(html: str, url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")
    data: Dict[str, Any] = {k: None for k in (
        "url", "title", "price_usd", "odometer", "username",
        "phone_number", "image_url", "images_count",
        "car_number", "car_vin",
        "fuel_type", "transmission", "engine_volume", "drive_type",
        "datetime_found",
    )}
    data["url"] = url
    data["datetime_found"] = datetime.now()

    # ── 1. ld+json — single reliable source for ~80 % of fields ──────────────
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            ld = json.loads(tag.string or "")
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(ld, dict):
            continue

        if not data["title"]:
            data["title"] = ld.get("name")

        # Price
        offers = ld.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if not data["price_usd"] and "price" in offers:
            try:
                data["price_usd"] = float(offers["price"])
            except (ValueError, TypeError):
                pass

        # Image
        if not data["image_url"]:
            imgs = ld.get("image", [])
            if isinstance(imgs, str):
                data["image_url"] = imgs
            elif isinstance(imgs, list) and imgs:
                data["image_url"] = imgs[0]

        # VIN / mileage via vehicleIdentificationNumber / mileageFromOdometer
        if not data["car_vin"] and len(ld.get("vehicleIdentificationNumber", "")) == 17:
            data["car_vin"] = ld["vehicleIdentificationNumber"]

        if not data["odometer"]:
            mileage = ld.get("mileageFromOdometer", {})
            if isinstance(mileage, dict):
                val = mileage.get("value")
                unit = mileage.get("unitCode", "")
                if val:
                    km = int(val) * 1000 if "тис" in str(unit).lower() else int(val)
                    data["odometer"] = km if km <= 1_000_000 else None

        # Technical specs present in AutoRia's ld+json as schema.org Car fields
        if not data["fuel_type"]:
            data["fuel_type"] = ld.get("fuelType")
        if not data["transmission"]:
            data["transmission"] = ld.get("vehicleTransmission")
        if not data["drive_type"]:
            data["drive_type"] = ld.get("driveWheelConfiguration")
        if not data["engine_volume"]:
            eng = ld.get("engineDisplacement") or ld.get("vehicleEngine", {})
            if isinstance(eng, dict):
                data["engine_volume"] = str(eng.get("engineDisplacement", "")) or None
            elif isinstance(eng, str) and eng:
                data["engine_volume"] = eng

    # ── 2. CSS fallbacks for anything still missing ───────────────────────────

    if not data["title"]:
        el = soup.select_one("h1.head, h1[class*='head'], h1")
        data["title"] = el.get_text(strip=True) if el else None

    if not data["price_usd"]:
        el = (soup.find(attrs={"data-currency": "USD"})
              or soup.select_one(".price_value strong")
              or soup.select_one(".price-ticket__usd"))
        if el:
            data["price_usd"] = _int(el.get_text())

    if not data["odometer"]:
        for node in soup.find_all(string=re.compile(r"\d+\s*тис\.?\s*км", re.I)):
            m = re.search(r"(\d+)\s*тис", str(node))
            if m:
                km = int(m.group(1)) * 1000
                if km <= 1_000_000:
                    data["odometer"] = km
                    break

    if not data["username"]:
        el = (soup.select_one(".seller_info_name")
              or soup.select_one(".seller-info__name"))
        data["username"] = el.get_text(strip=True) if el else None

    if not data["image_url"]:
        el = soup.select_one(".photo-620x465 img, .gallery-order__item img")
        if el:
            data["image_url"] = el.get("src") or el.get("data-src")

    if not data["images_count"]:
        el = soup.select_one(".photo-count, [data-photo-count]")
        if el:
            data["images_count"] = _int(el.get("data-photo-count") or el.get_text())

    if not data["car_number"]:
        el = soup.select_one(".state-num, .auto-number")
        data["car_number"] = el.get_text(strip=True) if el else None

    if not data["car_vin"]:
        el = soup.select_one(".label-vin, [data-vin], .vin-code")
        val = (el.get("data-vin") or el.get_text(strip=True)) if el else None
        if val and len(val) == 17:
            data["car_vin"] = val

    # ── Technical specs fallback — #details characteristic table ─────────────
    # Auto.ria renders specs as <dd class="mhide"> inside #details.
    # We build a label→value map once and look up each field by Ukrainian label.
    details = soup.select_one("#details")
    if details:
        spec_map: Dict[str, str] = {}
        for item in details.select(".technical-info__item, .car-characteristics__item, dd"):
            label_el = item.select_one(".label, dt, .key")
            value_el = item.select_one(".argument, dd, .value")
            if label_el and value_el:
                spec_map[label_el.get_text(strip=True).lower()] = value_el.get_text(strip=True)

        def _spec(*keys: str) -> Optional[str]:
            for k in keys:
                for label, val in spec_map.items():
                    if k in label:
                        return val or None
            return None

        if not data["fuel_type"]:
            data["fuel_type"] = _spec("пальн", "паливо", "fuel")
        if not data["transmission"]:
            data["transmission"] = _spec("коробка", "кпп", "transmission")
        if not data["engine_volume"]:
            data["engine_volume"] = _spec("двигун", "об'єм", "engine")
        if not data["drive_type"]:
            data["drive_type"] = _spec("привід", "drive")

    # Phone: AutoRia loads numbers dynamically via XHR.
    # Extract lookup keys here; actual API call happens in the worker.
    btn = soup.find(attrs={"data-hash": True}) or soup.find(attrs={"data-phone-hash": True})
    if btn:
        data["_phone_meta"] = {
            "car_id":  btn.get("data-car-id") or btn.get("data-id"),
            "hash":    btn.get("data-hash") or btn.get("data-phone-hash"),
            "expires": btn.get("data-expires"),
        }

    return data

async def fetch_phone(session: aiohttp.ClientSession, meta: Dict) -> Optional[str]:
    """Call AutoRia phone API — requires session cookies from a real login."""
    car_id = meta.get("car_id")
    h      = meta.get("hash")
    exp    = meta.get("expires")
    if not (car_id and h):
        return None
    url = f"https://auto.ria.com/users/phones/{car_id}?hash={h}&expires={exp}"
    try:
        headers = {**HEADERS, "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                body = await r.json(content_type=None)
                phones = body.get("phones", [])
                if phones:
                    return re.sub(r"\D", "", phones[0].get("phoneFormatted", "")) or None
    except Exception as e:
        log.debug("Phone API error: %s", e)
    return None

# ── Producer / Consumer ───────────────────────────────────────────────────────

async def producer(session: aiohttp.ClientSession, queue: asyncio.Queue, workers: int) -> None:
    """Discover listing pages and push car URLs into the queue."""
    html = await fetch(session, START_URL)
    if not html:
        log.error("Cannot fetch start page — aborting")
        for _ in range(workers):
            await queue.put(None)
        return

    soup = BeautifulSoup(html, "lxml")
    total_pages = 1
    span = soup.find("span", class_="page-item")
    if span:
        m = re.search(r"з\s+(\d+)", span.get_text())
        if m:
            total_pages = int(m.group(1))
    links = [a for a in soup.find_all("a", class_="page-link") if a.get_text(strip=True).isdigit()]
    if links:
        total_pages = max(int(a.get_text(strip=True)) for a in links)

    log.info("Pages to scrape: %d", total_pages)

    for page in range(total_pages):
        url = START_URL.replace("page=0", f"page={page}")
        page_html = await fetch(session, url)
        if not page_html:
            continue
        s = BeautifulSoup(page_html, "lxml")
        for sec in s.find_all("section", class_="ticket-item"):
            tag = sec.find("a", class_="m-link-ticket")
            if tag and tag.get("href"):
                href = tag["href"]
                if not href.startswith("http"):
                    href = "https://auto.ria.com" + href
                await queue.put(href)          # blocks if queue is full ← memory control
        await asyncio.sleep(1)

    for _ in range(workers):                   # sentinel per worker
        await queue.put(None)
    log.info("Producer done")

async def worker(
    wid: int,
    session: aiohttp.ClientSession,
    queue: asyncio.Queue,
    pool: asyncpg.Pool,
    stats: Dict,
) -> None:
    """Pull URLs from the queue, parse, phone-fetch, and persist."""
    while True:
        url = await queue.get()
        if url is None:
            queue.task_done()
            break
        try:
            html = await fetch(session, url)
            if not html:
                stats["errors"] += 1
                continue

            car = parse_car(html, url)

            # Resolve phone if we have the lookup keys
            meta = car.pop("_phone_meta", None)
            if meta:
                car["phone_number"] = await fetch_phone(session, meta)

            is_new = await save_car(pool, car)
            key = "new" if is_new else "updated"
            stats[key] += 1
            log.info("[W%d] %s — %s", wid, key.upper(), car.get("title", url))

        except Exception as e:
            log.error("[W%d] Error on %s: %s", wid, url, e)
            stats["errors"] += 1
        finally:
            stats["total"] += 1
            queue.task_done()

# ── Daily dump ────────────────────────────────────────────────────────────────

def pg_dump() -> None:
    """Run pg_dump and save to DUMP_DIR. Called from the scheduler task."""
    os.makedirs(DUMP_DIR, exist_ok=True)
    filename = datetime.now().strftime("dump_%Y%m%d_%H%M.sql")
    path = os.path.join(DUMP_DIR, filename)
    env = {**os.environ, "PGPASSWORD": os.getenv("POSTGRES_PASSWORD", "")}
    result = subprocess.run(
        ["pg_dump",
         "-h", os.getenv("POSTGRES_HOST", "db"),
         "-U", os.getenv("POSTGRES_USER", "user"),
         "-d", os.getenv("POSTGRES_DB",   "autoria"),
         "-f", path],
        env=env, capture_output=True, text=True,
    )
    if result.returncode == 0:
        log.info("Dump saved → %s", path)
    else:
        log.error("pg_dump failed: %s", result.stderr)

async def dump_scheduler() -> None:
    """Await until DUMP_TIME (12:00) then trigger pg_dump, repeat daily."""
    from datetime import timedelta
    while True:
        now = datetime.now()
        target = now.replace(hour=DUMP_TIME.hour, minute=DUMP_TIME.minute, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)   # timedelta handles month/year rollover correctly
        wait = (target - now).total_seconds()
        log.info("Next dump in %.0f s (at %s)", wait, target.strftime("%Y-%m-%d %H:%M"))
        await asyncio.sleep(wait)
        await asyncio.get_event_loop().run_in_executor(None, pg_dump)

# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    await init_db(pool)

    stats = {"total": 0, "new": 0, "updated": 0, "errors": 0}
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    async with aiohttp.ClientSession() as session:
        # Background daily dump
        asyncio.create_task(dump_scheduler())

        # Launch producer + workers concurrently
        await asyncio.gather(
            producer(session, queue, NUM_WORKERS),
            *[worker(i, session, queue, pool, stats) for i in range(NUM_WORKERS)],
        )

    await pool.close()
    log.info("Done — %s", stats)


if __name__ == "__main__":
    import sys
    if "--dump" in sys.argv:
        pg_dump()
    else:
        asyncio.run(main())

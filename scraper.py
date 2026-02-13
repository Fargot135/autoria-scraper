import asyncio
import json
import logging
import os
import random
import re
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
import asyncpg
from bs4 import BeautifulSoup

from database import save_car

log = logging.getLogger("autoria")

START_URL   = os.getenv("START_URL", "https://auto.ria.com/uk/search/?indexName=auto&page=0")
NUM_WORKERS = int(os.getenv("NUM_WORKERS", "5"))

# ── Browser profiles ─────────────────────────────────────────────────────────

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

# ── HTTP ──────────────────────────────────────────────────────────────────────

async def fetch(session: aiohttp.ClientSession, url: str, retries: int = 3) -> Optional[str]:
    """GET with exponential back-off on 429 / 5xx."""
    delay = 1.0
    for attempt in range(retries):
        await asyncio.sleep(random.uniform(0.2, 0.6))
        try:
            headers = {**random.choice(BROWSER_PROFILES), "Referer": "https://auto.ria.com/"}
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status == 200:
                    return await r.text()
                if r.status in (429, 500, 502, 503, 504):
                    retry_after = r.headers.get("Retry-After", "")
                    try:
                        wait = min(float(retry_after), 60) if retry_after.isdigit() else delay
                    except (ValueError, AttributeError):
                        wait = delay
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


def _url_from_image(obj: Any) -> Optional[str]:
    """Unwrap any ld+json image value (str / ImageObject dict / list) to a plain URL."""
    if isinstance(obj, str):
        return obj or None
    if isinstance(obj, dict):
        return obj.get("url") or obj.get("contentUrl") or obj.get("image") or None
    if isinstance(obj, list) and obj:
        return _url_from_image(obj[0])
    return None


def parse_car(html: str, url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")

    # All 12 mandatory fields + 4 bonus technical specs initialised to None
    data: Dict[str, Any] = {k: None for k in (
        "url", "title", "price_usd", "odometer", "username",
        "phone_number", "image_url", "images_count",
        "car_number", "car_vin",
        "fuel_type", "transmission", "engine_volume", "drive_type",
        "datetime_found",
    )}
    data["url"] = url
    data["datetime_found"] = datetime.now()

    # ── Pass 1: ld+json (stable, ~80 % of fields) ────────────────────────────
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            ld = json.loads(tag.string or "")
        except (json.JSONDecodeError, ValueError):
            continue

        # AutoRia sometimes wraps the Car object in a list: [{...}] or [@graph:[...]]
        if isinstance(ld, list):
            ld = next((item for item in ld if isinstance(item, dict)), {})
        if not isinstance(ld, dict):
            continue

        if not data["title"]:
            data["title"] = ld.get("name")

        offers = ld.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if not data["price_usd"] and "price" in offers:
            try:
                data["price_usd"] = float(offers["price"])
            except (ValueError, TypeError):
                pass

        if not data["image_url"]:
            data["image_url"] = _url_from_image(ld.get("image"))

        if not data["car_vin"] and len(ld.get("vehicleIdentificationNumber", "")) == 17:
            data["car_vin"] = ld["vehicleIdentificationNumber"]

        if not data["odometer"]:
            mileage = ld.get("mileageFromOdometer", {})
            if isinstance(mileage, dict):
                raw_value = mileage.get("value")
                if raw_value is not None:
                    try:
                        
                        cleaned = str(raw_value).strip().replace(" ", "").replace("\xa0", "")
                        val = int(cleaned.split(".")[0])
                        
                        unit_code = str(mileage.get("unitCode", "")).lower()
                        
                        
                        is_thousands = (
                            "тис" in unit_code or 
                            "тис" in str(raw_value).lower()
                        )
                        
                        if is_thousands:
                            km = val * 1000
                        else:
                            km = val
                        
                        
                        if 0 <= km <= 2_000_000:
                            data["odometer"] = km
                        else:
                            log.warning("Odometer %d km out of realistic range for %s", km, url)
                            
                    except (ValueError, TypeError) as e:
                        log.debug("Odometer parse error: %s", e)

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

    # ── Pass 2: CSS / meta fallbacks ─────────────────────────────────────────

    # Title: og:title → h1 selectors → URL slug (last resort, never None)
    if not data["title"]:
        og = soup.find("meta", property="og:title")
        if og and og.get("content", "").strip():
            data["title"] = og["content"].strip()

    if not data["title"]:
        el = (soup.select_one("h1.head")
              or soup.select_one("h1.ticket-title")
              or soup.select_one("h1[class*='head']")
              or soup.select_one("h1"))
        if el:
            data["title"] = el.get_text(strip=True) or None

    if not data["title"]:
        m = re.search(r"/auto_([^/]+?)_\d+\.html", url)
        if m:
            data["title"] = m.group(1).replace("_", " ").title()
            log.debug("Title from URL slug: %s", data["title"])

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
                if km <= 2_000_000:
                    data["odometer"] = km
                    break
        
        if not data["odometer"]:
            for node in soup.find_all(string=re.compile(r"\d[\d\s]+км", re.I)):
                text = re.sub(r"\s", "", str(node))   
                m = re.search(r"(\d+)км", text)
                if m:
                    km = int(m.group(1))
                    if 100 <= km <= 2_000_000:
                        data["odometer"] = km
                        break

    if not data["username"]:
        el = soup.select_one(".seller_info_name, .seller-info__name")
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

    # Technical specs: label→value map from #details block
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
            data["fuel_type"]    = _spec("пальн", "паливо", "fuel")
        if not data["transmission"]:
            data["transmission"] = _spec("коробка", "кпп", "transmission")
        if not data["engine_volume"]:
            data["engine_volume"]= _spec("двигун", "об'єм", "engine")
        if not data["drive_type"]:
            data["drive_type"]   = _spec("привід", "drive")

    
    btn = soup.find(attrs={"data-hash": True}) or soup.find(attrs={"data-phone-hash": True})
    if btn:
        data["_phone_meta"] = {
            "car_id":  btn.get("data-car-id") or btn.get("data-id"),
            "hash":    btn.get("data-hash")   or btn.get("data-phone-hash"),
            "expires": btn.get("data-expires"),
        }

    return data


async def fetch_phone(session: aiohttp.ClientSession, meta: Dict) -> Optional[str]:
    """
    Call AutoRia phone API. Returns phone string or None.
    Caller (worker) applies the "38000{car_id}" fallback via save_car.
    """
    car_id = meta.get("car_id")
    h      = meta.get("hash")
    exp    = meta.get("expires")
    if not (car_id and h):
        return None
    api_url = f"https://auto.ria.com/users/phones/{car_id}?hash={h}&expires={exp}"
    try:
        api_headers = {**HEADERS, "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}
        async with session.get(api_url, headers=api_headers, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                body   = await r.json(content_type=None)
                phones = body.get("phones", [])
                if phones:
                    number = re.sub(r"\D", "", phones[0].get("phoneFormatted", ""))
                    return number or None
    except Exception as e:
        log.warning("Phone API error for car_id=%s: %s", car_id, e)
    return None

# ── Producer ──────────────────────────────────────────────────────────────────

async def producer(session: aiohttp.ClientSession, queue: asyncio.Queue, workers: int) -> None:
    """Discover listing pages and push car URLs into the bounded queue."""
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
    page_links = [a for a in soup.find_all("a", class_="page-link") if a.get_text(strip=True).isdigit()]
    if page_links:
        total_pages = max(int(a.get_text(strip=True)) for a in page_links)

    log.info("Pages to scrape: %d", total_pages)

    car_url_re = re.compile(r"(/auto_[^\"'\s]+\.html)", re.IGNORECASE)
    seen: set = set()

    for page in range(total_pages):
        page_url  = START_URL.replace("page=0", f"page={page}")
        page_html = await fetch(session, page_url)
        if not page_html:
            log.warning("Producer: empty page %d — skipping", page)
            continue

        found = 0
        for tag in BeautifulSoup(page_html, "lxml").find_all("a", href=car_url_re):
            href = tag["href"]
            if not href.startswith("http"):
                href = "https://auto.ria.com" + href
            href = href.split("?")[0].split("#")[0]   # strip tracking params
            if href in seen:
                continue
            seen.add(href)
            await queue.put(href)   # back-pressure: blocks when queue is full
            found += 1

        log.info("Producer: page %d → %d new URLs (queued total: %d)", page, found, len(seen))
        await asyncio.sleep(1)

    for _ in range(workers):
        await queue.put(None)   
    log.info("Producer done — %d unique car URLs discovered", len(seen))

# ── Worker ────────────────────────────────────────────────────────────────────

async def worker(
    wid: int,
    session: aiohttp.ClientSession,
    queue: asyncio.Queue,
    pool: asyncpg.Pool,
    stats: Dict,
) -> None:
    """Pull URLs from the queue, parse, phone-resolve, and persist."""
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

            car  = parse_car(html, url)
            meta = car.pop("_phone_meta", None)
            if meta:
                car["phone_number"] = await fetch_phone(session, meta)
            

            is_new = await save_car(pool, car)
            stats["new" if is_new else "updated"] += 1
            log.info("[W%d] %s — %s", wid, "NEW" if is_new else "UPD", car.get("title", url))

        except Exception as e:
            log.error("[W%d] Error on %s: %s", wid, url, e)
            stats["errors"] += 1
        finally:
            stats["total"] += 1
            queue.task_done()


async def run_scrape(pool: asyncpg.Pool) -> Dict[str, int]:
    """Run one full scrape cycle. Called by main.py scheduler."""
    stats: Dict[str, int] = {"total": 0, "new": 0, "updated": 0, "errors": 0}
    queue: asyncio.Queue  = asyncio.Queue(maxsize=100)

    async with aiohttp.ClientSession() as session:
        await asyncio.gather(
            producer(session, queue, NUM_WORKERS),
            *[worker(i, session, queue, pool, stats) for i in range(NUM_WORKERS)],
        )

    return stats
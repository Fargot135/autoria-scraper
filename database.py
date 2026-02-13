import logging
import os
from typing import Dict

import asyncpg
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("autoria")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/autoria")


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cars (
    id              SERIAL PRIMARY KEY,
    url             TEXT UNIQUE NOT NULL,
    title           TEXT,
    price_usd       NUMERIC,
    odometer        INTEGER,
    username        TEXT,
    phone_number    BIGINT NOT NULL,        -- never null: fallback = "38000" + car_id
    image_url       TEXT,
    images_count    INTEGER,
    car_number      TEXT,
    car_vin         TEXT,
    datetime_found  TIMESTAMP DEFAULT NOW()
);
"""

UPSERT_SQL = """
INSERT INTO cars (url, title, price_usd, odometer, username, phone_number,
                  image_url, images_count, car_number, car_vin)
VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
ON CONFLICT (url) DO UPDATE SET
    title          = EXCLUDED.title,
    price_usd      = EXCLUDED.price_usd,
    odometer       = EXCLUDED.odometer,
    username       = EXCLUDED.username,
    phone_number   = EXCLUDED.phone_number,
    image_url      = EXCLUDED.image_url,
    images_count   = EXCLUDED.images_count,
    car_number     = EXCLUDED.car_number,
    car_vin        = EXCLUDED.car_vin
RETURNING (xmax = 0) AS is_insert;
"""


async def create_pool() -> asyncpg.Pool:
    """Create and return the shared connection pool."""
    return await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)


async def init_db(pool: asyncpg.Pool) -> None:
    """Create table if it doesn't exist."""
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLE_SQL)


async def save_car(pool: asyncpg.Pool, d: Dict) -> bool:
    """Upsert one car. Returns True if it was a new insert.

    Column → parameter mapping is explicit ($N comments) so any future
    column addition is immediately visible as a positional shift.
    """
    # ── Mandatory field guards 
    if not d.get("url"):
        log.error("save_car: record has no URL — skipping")
        return False

    if not d.get("title"):
        log.warning("save_car: no title for %s — using 'N/A'", d["url"])
        d["title"] = "N/A"


    if not d.get("phone_number"):
        import re as _re
        m = _re.search(r"_(\d+)\.html$", d.get("url", ""))
        car_id = m.group(1) if m else "0"
        d["phone_number"] = int(f"38000{car_id}")
        log.warning("save_car: phone fallback for %s → %s", d["url"], d["phone_number"])

    params = (
        d["url"],            
        d["title"],          
        d["price_usd"],      
        d["odometer"],       
        d["username"],       
        d["phone_number"],   
        d["image_url"],      
        d["images_count"],   
        d["car_number"],    
        d["car_vin"],        
        
    )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(UPSERT_SQL, *params)
        return row["is_insert"] if row else False
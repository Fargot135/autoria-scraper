import asyncpg
import os
from typing import Optional

class Database:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None
        
    async def connect(self):
        """Create database connection pool"""
        self.pool = await asyncpg.create_pool(
            host=os.getenv('DB_HOST', 'localhost'),
            port=int(os.getenv('DB_PORT', 5432)),
            database=os.getenv('DB_NAME', 'autoria'),
            user=os.getenv('DB_USER', 'autoria_user'),
            password=os.getenv('DB_PASSWORD', 'autoria_password'),
            min_size=5,
            max_size=20
        )
        await self.init_db()
        
    async def init_db(self):
        """Initialize database schema"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS cars (
                    id SERIAL PRIMARY KEY,
                    url TEXT UNIQUE NOT NULL,
                    title TEXT,
                    price_usd NUMERIC,
                    odometer INTEGER,
                    username TEXT,
                    phone_number TEXT,
                    image_url TEXT,
                    images_count INTEGER,
                    car_number TEXT,
                    car_vin TEXT,
                    datetime_found TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_url ON cars(url);
                CREATE INDEX IF NOT EXISTS idx_datetime_found ON cars(datetime_found);
            ''')
    
    async def insert_or_update_car(self, car_data: dict) -> bool:
        """Insert new car or update if exists. Returns True if inserted, False if updated"""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(
                'SELECT id FROM cars WHERE url = $1',
                car_data['url']
            )
            
            if result:
                await conn.execute('''
                    UPDATE cars SET
                        title = $2,
                        price_usd = $3,
                        odometer = $4,
                        username = $5,
                        phone_number = $6,
                        image_url = $7,
                        images_count = $8,
                        car_number = $9,
                        car_vin = $10,
                        datetime_found = $11,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE url = $1
                ''', car_data['url'], car_data.get('title'), car_data.get('price_usd'),
                    car_data.get('odometer'), car_data.get('username'), car_data.get('phone_number'),
                    car_data.get('image_url'), car_data.get('images_count'), car_data.get('car_number'),
                    car_data.get('car_vin'), car_data.get('datetime_found'))
                return False
            else:
                await conn.execute('''
                    INSERT INTO cars (url, title, price_usd, odometer, username, phone_number, 
                                    image_url, images_count, car_number, car_vin, datetime_found)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ''', car_data['url'], car_data.get('title'), car_data.get('price_usd'),
                    car_data.get('odometer'), car_data.get('username'), car_data.get('phone_number'),
                    car_data.get('image_url'), car_data.get('images_count'), car_data.get('car_number'),
                    car_data.get('car_vin'), car_data.get('datetime_found'))
                return True
    
    async def close(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()

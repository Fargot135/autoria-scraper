import asyncio
import os
import logging
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from database import create_pool, init_db
from scraper import run_scrape
from dump_manager import DumpManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AutoRiaApp:
    def __init__(self):
        load_dotenv()
        
        self.pool = None
        self.dump_manager = DumpManager()
        self.scheduler = AsyncIOScheduler()
        
        # Read hour and minute from .env
        scrape_hour = int(os.getenv('SCRAPE_HOUR', '12'))
        scrape_minute = int(os.getenv('SCRAPE_MINUTE', '0'))
        dump_hour = int(os.getenv('DUMP_HOUR', '12'))
        dump_minute = int(os.getenv('DUMP_MINUTE', '0'))
        
        # Schedule scraping
        self.scheduler.add_job(
            self.run_scraping,
            CronTrigger(hour=scrape_hour, minute=scrape_minute),
            id='scraping_job',
            name='Daily scraping job',
            replace_existing=True
        )
        
        # Schedule database dump
        self.scheduler.add_job(
            self.run_dump,
            CronTrigger(hour=dump_hour, minute=dump_minute),
            id='dump_job',
            name='Daily dump job',
            replace_existing=True
        )
        
        logger.info(f"Scraping scheduled at {scrape_hour:02d}:{scrape_minute:02d}")
        logger.info(f"Database dump scheduled at {dump_hour:02d}:{dump_minute:02d}")
    
    async def run_scraping(self):
        """Execute scraping task"""
        logger.info("Starting scheduled scraping...")
        try:
            stats = await run_scrape(self.pool)
            logger.info(f"Scraping completed. Stats: {stats}")
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}", exc_info=True)
    
    async def run_dump(self):
        """Execute database dump"""
        logger.info("Starting scheduled database dump...")
        try:
            dump_file = await self.dump_manager.create_dump()
            if dump_file:
                logger.info(f"Dump completed: {dump_file}")
            else:
                logger.error("Dump failed")
        except Exception as e:
            logger.error(f"Error during dump: {str(e)}", exc_info=True)
    
    async def run(self):
        """Main application loop"""
        logger.info("Initializing AutoRia scraper application...")
        
        # Create database pool
        self.pool = await create_pool()
        logger.info("Database pool created")
        
        # Initialize database schema
        await init_db(self.pool)
        logger.info("Database initialized")
        
        # Check if we should run initial scraping (useful flag for testing)
        run_on_startup = os.getenv('RUN_ON_STARTUP', 'false').lower() == 'true'
        
        if run_on_startup:
            # Run initial scraping on startup
            logger.info("Running initial scraping on startup...")
            await self.run_scraping()
            
            # Run initial dump
            logger.info("Running initial dump on startup...")
            await self.run_dump()
        else:
            logger.info("Skipping initial scraping (RUN_ON_STARTUP=false). Waiting for scheduled time...")
        
        # Start scheduler
        self.scheduler.start()
        logger.info("Scheduler started")
        
        try:
            # Keep the application running
            while True:
                await asyncio.sleep(60)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutting down...")
            self.scheduler.shutdown()
            if self.pool:
                await self.pool.close()
                logger.info("Database pool closed")

if __name__ == '__main__':
    app = AutoRiaApp()
    asyncio.run(app.run())
import asyncio
import os
import logging
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from database import Database
from scraper import AutoRiaScraper
from dump_manager import DumpManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AutoRiaApp:
    def __init__(self):
        load_dotenv()
        
        self.db = Database()
        self.dump_manager = DumpManager()
        self.scheduler = AsyncIOScheduler()
        
        self.start_url = os.getenv('START_URL', 
            'https://auto.ria.com/uk/search/?categories.main.id=1&indexName=auto,order_auto,newauto_search&country.import.usa.not=-1&price.currency=1&abroad.not=0&custom.not=1&page=0&size=100')
        
        scrape_time = os.getenv('SCRAPE_TIME', '12:00')
        dump_time = os.getenv('DUMP_TIME', '12:00')
        
        # Parse times
        scrape_hour, scrape_minute = map(int, scrape_time.split(':'))
        dump_hour, dump_minute = map(int, dump_time.split(':'))
        
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
        
        logger.info(f"Scraping scheduled at {scrape_time}")
        logger.info(f"Database dump scheduled at {dump_time}")
    
    async def run_scraping(self):
        """Execute scraping task"""
        logger.info("Starting scheduled scraping...")
        try:
            async with AutoRiaScraper(self.start_url, max_concurrent_requests=15) as scraper:
                stats = await scraper.scrape_all(self.db)
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
        
        # Connect to database
        await self.db.connect()
        logger.info("Database connected")
        
        # Run initial scraping on startup
        logger.info("Running initial scraping on startup...")
        await self.run_scraping()
        
        # Run initial dump
        logger.info("Running initial dump on startup...")
        await self.run_dump()
        
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
            await self.db.close()

if __name__ == '__main__':
    app = AutoRiaApp()
    asyncio.run(app.run())

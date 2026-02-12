import os
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class DumpManager:
    def __init__(self, dumps_dir: str = '/app/dumps'):
        self.dumps_dir = dumps_dir
        os.makedirs(dumps_dir, exist_ok=True)
    
    async def create_dump(self):
        """Create PostgreSQL database dump"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        dump_file = os.path.join(self.dumps_dir, f'autoria_dump_{timestamp}.sql')
        
        db_host = os.getenv('DB_HOST', 'localhost')
        db_port = os.getenv('DB_PORT', '5432')
        db_name = os.getenv('DB_NAME', 'autoria')
        db_user = os.getenv('DB_USER', 'autoria_user')
        db_password = os.getenv('DB_PASSWORD', 'autoria_password')
        
        env = os.environ.copy()
        env['PGPASSWORD'] = db_password
        
        cmd = f'pg_dump -h {db_host} -p {db_port} -U {db_user} -d {db_name} -F p -f {dump_file}'
        
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"Database dump created successfully: {dump_file}")
                return dump_file
            else:
                logger.error(f"Failed to create dump: {stderr.decode()}")
                return None
        except Exception as e:
            logger.error(f"Error creating dump: {str(e)}")
            return None

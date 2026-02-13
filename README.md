# 🚗 AutoRia Scraper

Asynchronous application for automatic scraping of used car listings from the AutoRia platform with daily data storage in PostgreSQL and automated database backups.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791.svg)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)
![Async](https://img.shields.io/badge/Async-aiohttp-00ADD8.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## 📋 Table of Contents

- [Features](#-features)
- [Technologies](#-technologies)
- [Installation](#-installation)
- [Usage](#-usage)
- [Project Structure](#-project-structure)
- [Configuration](#-configuration)
- [Database Schema](#-database-schema)
- [Monitoring](#-monitoring)
- [Troubleshooting](#-troubleshooting)
- [Author](#-author)

---

## ✨ Features

### 🚀 Performance

- **Asynchronous scraping** - utilizing `aiohttp` for parallel HTTP requests
- **Multi-threading** - efficient processing of large page volumes
- **Connection pooling** - optimized database operations via `asyncpg`
- **Batch processing** - minimized database load

### 📊 Functionality

- ✅ Daily automatic execution at configured time
- ✅ Complete data collection (URL, price, mileage, phone, VIN, etc.)
- ✅ Duplicate prevention mechanism
- ✅ Automated database backups
- ✅ Docker Compose for easy deployment
- ✅ Detailed process logging
- ✅ Configurable worker count for parallel scraping
- ✅ Optional startup execution

### 🛡️ Reliability

- Error handling with retry mechanisms
- Data validation before storage
- Automated database backups
- Comprehensive logging for monitoring

---

## 🛠️ Technologies

### Backend & Database

- **Python 3.11+** - Programming language
- **PostgreSQL 15** - Relational database
- **Docker & Docker Compose** - Containerization

### Python Libraries

```python
aiohttp==3.12.15      # Asynchronous HTTP requests
beautifulsoup4==4.14.3 # HTML parsing
asyncpg==0.30.0       # Async PostgreSQL driver
apscheduler==3.11.0   # Task scheduler
python-dotenv==1.2.1  # Environment management
brotli==1.1.0         # Content decompression
lxml==5.3.0           # Fast XML/HTML parser
```

---

## 🚀 Installation

### Prerequisites

- **Docker** and **Docker Compose** installed on your system
- **Git** for repository cloning

### Step 1: Clone the repository

```bash
git clone https://github.com/your-username/autoria-scraper.git
cd autoria-scraper
```

### Step 2: Create .env file

Create a `.env` file in the project root directory:

```properties
# ── Database ──────────────────────────────────────────────────
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_USER=autoria_user
POSTGRES_PASSWORD=strongpassword123
POSTGRES_DB=autoria

DATABASE_URL=postgresql://autoria_user:strongpassword123@db:5432/autoria

# ── Scraper ───────────────────────────────────────────────────
START_URL=https://auto.ria.com/uk/search/?indexName=auto&category_id=1&price_ot=1&price_do=100000&page=0
NUM_WORKERS=5

# Execution control
RUN_ON_STARTUP=true

# Scraping schedule
SCRAPE_HOUR=12
SCRAPE_MINUTE=0

# ── Dumps ─────────────────────────────────────────────────────
DUMP_DIR=/dumps
DUMP_HOUR=12
DUMP_MINUTE=0
```

**⚠️ Important:** Change `POSTGRES_PASSWORD` to a strong, secure password!

### Step 3: Launch the application

```bash
docker-compose up -d
```

---

## 💻 Usage

### Basic Docker Compose Commands

#### Start the application

```bash
docker-compose up -d
```

#### View logs in real-time

```bash
docker-compose logs -f scraper
```

#### Stop the application

```bash
docker-compose down
```

#### Complete removal (including data)

```bash
docker-compose down -v
```

### Local Execution (without Docker)

1. **Install PostgreSQL** and create database:

```sql
CREATE DATABASE autoria;
CREATE USER autoria_user WITH PASSWORD 'strongpassword123';
GRANT ALL PRIVILEGES ON DATABASE autoria TO autoria_user;
```

2. **Install dependencies**:

```bash
pip install -r requirements.txt
```

3. **Configure .env** (set `POSTGRES_HOST=localhost`)

4. **Run the application**:

```bash
python main.py
```

---

## 📁 Project Structure

```
autoria-scraper/
├── .env                    # Configuration file (create from example)
├── .env.example           # Configuration example
├── .gitignore             # Git ignored files
├── docker-compose.yml     # Docker Compose configuration
├── Dockerfile             # Application Docker image
├── requirements.txt       # Python dependencies
├── README.md              # Project documentation
│
├── database.py            # 🗄️ PostgreSQL operations
├── scraper.py             # 🕷️ AutoRia scraping logic
├── main.py                # 🚀 Entry point, task scheduler
├── dump_manager.py        # 💾 Database backup creation
│
└── dumps/                 # 📦 Database backups (auto-created)
```

---

## ⚙️ Configuration

### Environment Variables

| Parameter | Description | Example |
|-----------|-------------|---------|
| `POSTGRES_HOST` | Database host (`db` for Docker, `localhost` for local) | `db` |
| `POSTGRES_PORT` | PostgreSQL port | `5432` |
| `POSTGRES_USER` | Database user | `autoria_user` |
| `POSTGRES_PASSWORD` | Database password | `strongpassword123` |
| `POSTGRES_DB` | Database name | `autoria` |
| `DATABASE_URL` | Full connection string | `postgresql://user:pass@host:port/db` |
| `START_URL` | Starting URL for scraping | `https://auto.ria.com/...` |
| `NUM_WORKERS` | Number of parallel workers | `5` |
| `RUN_ON_STARTUP` | Execute scraping on startup | `true` / `false` |
| `SCRAPE_HOUR` | Hour to start daily scraping (0-23) | `12` |
| `SCRAPE_MINUTE` | Minute to start scraping (0-59) | `0` |
| `DUMP_DIR` | Directory for database dumps | `/dumps` |
| `DUMP_HOUR` | Hour to create database backup (0-23) | `12` |
| `DUMP_MINUTE` | Minute to create backup (0-59) | `0` |

**⚠️ Proxy Configuration (Highly Recommended):**

Add these to your `.env` for production use:

```properties
# Proxy settings (optional but recommended)
USE_PROXY=true
PROXY_URL=http://proxy-ip:port
PROXY_USERNAME=your_username
PROXY_PASSWORD=your_password

# Rate limiting
REQUEST_DELAY=2  # Seconds between requests
```

### Performance Tuning

- **NUM_WORKERS**: Increase for faster scraping (recommended: 3-10)
  - Lower values: More stable, less load
  - Higher values: Faster execution, more resources

- **RUN_ON_STARTUP**: 
  - `true` - Start scraping immediately on container launch
  - `false` - Wait for scheduled time

---

## 🗄️ Database Schema

### Table `cars`

| Field | Type | Description | Constraints |
|-------|------|-------------|-------------|
| `id` | SERIAL | Primary key | PRIMARY KEY |
| `url` | TEXT | Listing URL | UNIQUE, NOT NULL |
| `title` | TEXT | Car title/name | - |
| `price_usd` | INTEGER | Price in USD | - |
| `odometer` | INTEGER | - |
| `username` | TEXT | Seller's name | - |
| `phone_number` | BIGINT | Phone number (format 380XXXXXXXXX) | - |
| `image_url` | TEXT | Main image URL | - |
| `images_count` | INTEGER | Number of images | - |
| `car_number` | TEXT | License plate | - |
| `car_vin` | TEXT | VIN code | - |
| `datetime_found` | TIMESTAMP | Record creation timestamp | DEFAULT NOW() |

### Sample Data

```sql
url            | https://auto.ria.com/uk/auto_toyota_camry_12345678.html
title          | Toyota Camry 2020
price_usd      | 25000
odometer       | 45000
username       | Ivan Petrenko
phone_number   | 380501234567
image_url      | https://cdn.riastatic.com/...
images_count   | 15
car_number     | AA1234BB
car_vin        | 1HGBH41JXMN109186
datetime_found | 2026-02-13 12:00:00
```

---

## 📊 Monitoring

### Viewing Logs

**All logs in real-time:**
```bash
docker-compose logs -f scraper
```

**Last 100 lines:**
```bash
docker-compose logs --tail=100 scraper
```

**Database logs only:**
```bash
docker-compose logs -f db
```

### Database Connection

```bash
docker-compose exec db psql -U autoria_user -d autoria
```

### Useful SQL Queries

**Total record count:**
```sql
SELECT COUNT(*) FROM cars;
```

**Latest 10 added cars:**
```sql
SELECT url, title, price_usd, datetime_found 
FROM cars 
ORDER BY datetime_found DESC 
LIMIT 10;
```

**Price statistics:**
```sql
SELECT 
    AVG(price_usd) as avg_price,
    MIN(price_usd) as min_price,
    MAX(price_usd) as max_price
FROM cars
WHERE price_usd > 0;
```

**Most popular brands:**
```sql
SELECT 
    SPLIT_PART(title, ' ', 1) as brand,
    COUNT(*) as count
FROM cars
GROUP BY brand
ORDER BY count DESC
LIMIT 10;
```

**Cars added today:**
```sql
SELECT COUNT(*) 
FROM cars 
WHERE DATE(datetime_found) = CURRENT_DATE;
```

---

## 💾 Database Backups

### Automatic Backups

Dumps are created automatically daily at the time specified in `DUMP_HOUR` and `DUMP_MINUTE`.

**Location:** `dumps/`  
**Naming format:** `autoria_dump_YYYY-MM-DD_HH-MM-SS.sql`

### Manual Dump Creation

```bash
docker-compose exec scraper python dump_manager.py
```

### Restore from Dump

```bash
docker-compose exec -T db psql -U autoria_user -d autoria < dumps/autoria_dump_2026-02-13_12-00-00.sql
```

### Export Dump from Container

```bash
docker-compose exec db pg_dump -U autoria_user autoria > local_backup.sql
```

### List All Backups

```bash
ls -lh dumps/
```

---

## 🔧 Troubleshooting

### ❌ Application Won't Start

**Possible causes:**
- Incorrectly configured `.env` file
- Port 5432 occupied by another process
- Docker not running

**Solution:**
```bash
# Check container status
docker-compose ps

# View logs
docker-compose logs scraper

# Restart application
docker-compose restart
```

### ❌ Database Connection Errors

**Possible causes:**
- Database container not running
- Incorrect `POSTGRES_HOST` (should be `db` for Docker)
- Invalid credentials

**Solution:**
```bash
# Check if database is ready
docker-compose exec db pg_isready -U autoria_user

# View database logs
docker-compose logs db

# Restart database only
docker-compose restart db
```

### ❌ Dumps Not Being Created

**Possible causes:**
- Insufficient permissions for `dumps/` folder
- Invalid `DUMP_HOUR` or `DUMP_MINUTE` format
- Error in `dump_manager.py`

**Solution:**
```bash
# Create folder manually
mkdir -p dumps
chmod 755 dumps

# Check logs
docker-compose logs scraper | grep dump

# Create dump manually
docker-compose exec scraper python dump_manager.py
```

### ❌ Slow Scraping Performance

**Optimization:**
- Increase `NUM_WORKERS` in `.env` (recommended: 5-10)
- Use a more powerful server
- Check internet connection speed
- Monitor system resources

```bash
# Monitor resource usage
docker stats
```

### ❌ Duplicate Records

**Prevention:**
- Unique index on `url` field prevents duplicates automatically
- Check logs for `ON CONFLICT` messages
- Verify `url` field is being scraped correctly

### ❌ Getting Blocked / IP Banned

**Symptoms:**
- HTTP 403 Forbidden errors
- Requests timing out
- Captcha challenges
- Empty responses

**Solutions:**
```bash
# 1. Implement proxy rotation (recommended)
# Add proxy configuration to .env and modify scraper.py

# 2. Reduce scraping intensity
# In .env:
NUM_WORKERS=2  # Lower number of workers
REQUEST_DELAY=5  # Increase delay between requests

# 3. Change User-Agent
# Rotate User-Agent headers in scraper.py

# 4. Wait and retry later
# AutoRia may temporarily block, try again in a few hours
```

**Long-term solution:**
- Use rotating proxy service (see [Limitations](#️-important-limitations--recommendations))
- Implement exponential backoff
- Respect rate limits

---

## 📝 Notes

- 📌 The `dumps/` folder is created automatically on first run
- 📌 Listing URLs have a unique index - duplicates are automatically ignored
- 📌 All timestamps are stored in UTC
- 📌 Application automatically restarts on failure (Docker restart policy)
- 📌 Set `RUN_ON_STARTUP=false` to prevent scraping on container start
- 📌 Adjust `NUM_WORKERS` based on your server capacity

---

## ⚠️ Important Limitations & Recommendations

### Proxy Usage

**Critical:** This scraper **will likely get IP-banned** by AutoRia without proper proxy rotation.

**Why you need proxies:**
- AutoRia has rate limiting and anti-scraping protection
- Multiple requests from same IP will trigger blocking
- Large-scale scraping requires IP rotation

**Recommended solutions:**

1. **Use rotating proxy services:**
   - [Bright Data](https://brightdata.com/)
   - [Oxylabs](https://oxylabs.io/)
   - [ScraperAPI](https://www.scraperapi.com/)
   - [Smartproxy](https://smartproxy.com/)

2. **Free alternatives (limited):**
   - Free proxy lists (unreliable, frequently blocked)
   - Tor network (very slow, not recommended for scraping)

3. **Self-hosted solution:**
   - Multiple VPS instances with different IPs
   - Cloud provider IP rotation (AWS, GCP, Azure)

**Implementation note:**
To add proxy support, modify `scraper.py`:

```python
# Example with aiohttp
async with aiohttp.ClientSession() as session:
    proxy = "http://proxy-ip:port"
    proxy_auth = aiohttp.BasicAuth('username', 'password')
    
    async with session.get(url, proxy=proxy, proxy_auth=proxy_auth) as response:
        html = await response.text()
```

### Rate Limiting

Even with proxies, implement proper rate limiting:
- Add delays between requests (1-3 seconds recommended)
- Randomize request timing
- Respect `robots.txt`
- Use User-Agent rotation

### Legal & Ethical Considerations

⚖️ **Important:**
- Check AutoRia's Terms of Service before scraping
- Respect `robots.txt` file
- Don't overload their servers
- Use scraped data responsibly
- Consider using official APIs if available

### Production Deployment Checklist

Before deploying to production:

- [ ] Implement proxy rotation
- [ ] Add rate limiting/throttling
- [ ] Set up error monitoring (Sentry, etc.)
- [ ] Configure proper logging
- [ ] Implement retry logic with exponential backoff
- [ ] Add health checks
- [ ] Set up alerts for failures
- [ ] Test with small dataset first
- [ ] Monitor resource usage
- [ ] Plan for scaling

---

## 🚀 Advanced Usage

### Custom Scraping Schedule

Edit `.env` to run multiple times per day:
```properties
SCRAPE_HOUR=12
SCRAPE_MINUTE=0
```

### Database Maintenance

**Vacuum database:**
```bash
docker-compose exec db psql -U autoria_user -d autoria -c "VACUUM ANALYZE cars;"
```

**Check database size:**
```bash
docker-compose exec db psql -U autoria_user -d autoria -c "SELECT pg_size_pretty(pg_database_size('autoria'));"
```

---

## 🤝 Contributing

This project was created as a test assignment. Any suggestions for improvement are welcome!

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request


**Test Assignment for Python Developer Position**

## 📜 License

This project is created for educational and demonstration purposes.

---

<div align="center">

**Built with ❤️ using Python and Docker**


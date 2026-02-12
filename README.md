# AutoRia Scraper

Застосунок для щоденного автоматичного збору даних про автомобілі з платформи AUTO.RIA.

## Структура проекту

```
autoria_scraper/
├── main.py              # Точка входу, планувальник задач
├── database.py          # Робота з PostgreSQL
├── scraper.py           # Логіка скрапінгу
├── dump_manager.py      # Створення дампів БД
├── requirements.txt     # Python залежності
├── Dockerfile           # Docker образ
├── docker-compose.yml   # Оркестрація контейнерів
├── .env.example         # Приклад налаштувань
├── .env                 # Налаштування (створити вручну)
├── dumps/               # Папка для дампів БД (створюється автоматично)
└── README.md           # Документація
```

## Технології

- Python 3.11
- PostgreSQL 15
- Docker & Docker Compose
- Асинхронні бібліотеки: aiohttp, asyncpg
- BeautifulSoup4 для парсингу HTML
- APScheduler для планування задач

## Поля бази даних

Застосунок збирає наступні поля для кожного автомобіля:

- `url` - посилання на оголошення
- `title` - назва автомобіля
- `price_usd` - ціна в доларах США
- `odometer` - пробіг (в метрах, 95000 км = 95000000 м)
- `username` - ім'я продавця
- `phone_number` - номер телефону
- `image_url` - URL головного зображення
- `images_count` - кількість фотографій
- `car_number` - номерний знак
- `car_vin` - VIN-код
- `datetime_found` - дата збереження в базу

## Налаштування

1. Створіть файл `.env` на основі `.env.example`:

```bash
cp .env.example .env
```

2. Відредагуйте `.env` за потреби:

```env
DB_HOST=db
DB_PORT=5432
DB_NAME=autoria
DB_USER=autoria_user
DB_PASSWORD=autoria_password

SCRAPE_TIME=12:00
DUMP_TIME=12:00

START_URL=https://auto.ria.com/uk/search/?categories.main.id=1&indexName=auto,order_auto,newauto_search&country.import.usa.not=-1&price.currency=1&abroad.not=0&custom.not=1&page=0&size=100
```

## Запуск

### Попередні вимоги

- Docker
- Docker Compose

### Крок 1: Клонування репозиторію

```bash
git clone <repository-url>
cd autoria_scraper
```

### Крок 2: Налаштування

Створіть файл `.env`:

```bash
cp .env.example .env
```

### Крок 3: Запуск застосунку

```bash
docker-compose up -d
```

Застосунок:
- Створить базу даних
- Виконає перший скрапінг відразу після запуску
- Створить перший дамп БД
- Почне працювати за розкладом

### Крок 4: Перегляд логів

```bash
docker-compose logs -f scraper
```

### Зупинка застосунку

```bash
docker-compose down
```

### Зупинка з видаленням даних

```bash
docker-compose down -v
```

## Функціональність

### Скрапінг

- Виконується щодня о `SCRAPE_TIME`
- Проходить всі сторінки результатів пошуку
- Збирає дані з кожної картки авто
- Використовує асинхронність для швидкості (до 15 одночасних запитів)
- Запобігає дублюванню (за URL)
- При повторному знаходженні оновлює дані

### Дампи бази даних

- Створюються щодня о `DUMP_TIME`
- Зберігаються в папці `dumps/`
- Формат: `autoria_dump_YYYYMMDD_HHMMSS.sql`
- Можуть бути використані для відновлення БД

### Відновлення з дампу

```bash
docker exec -i autoria_db psql -U autoria_user -d autoria < dumps/autoria_dump_YYYYMMDD_HHMMSS.sql
```

## Продуктивність

Застосунок оптимізований для швидкості:

- Асинхронні HTTP-запити (aiohttp)
- Асинхронна робота з БД (asyncpg)
- Паралельна обробка сторінок
- Connection pooling для БД
- Семафор для контролю одночасних запитів

## Безпека

- Паролі та налаштування в `.env`
- `.env` виключений з Git (`.gitignore`)
- Використання Docker для ізоляції
- Індекси БД для швидкого пошуку

## Підтримка

Перевірте логи для діагностики:

```bash
docker-compose logs scraper
docker-compose logs db
```

Підключення до БД:

```bash
docker exec -it autoria_db psql -U autoria_user -d autoria
```

Запити до БД:

```sql
-- Кількість записів
SELECT COUNT(*) FROM cars;

-- Останні додані авто
SELECT title, price_usd, datetime_found FROM cars ORDER BY created_at DESC LIMIT 10;

-- Перевірка дублів
SELECT url, COUNT(*) FROM cars GROUP BY url HAVING COUNT(*) > 1;
```

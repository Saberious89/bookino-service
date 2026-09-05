# راهنمای فارسی راه‌اندازی بک‌اند و دیتابیس بوکینو روی هاست

این راهنما برای فردی نوشته شده است که برنامه‌نویس نیست، اما می‌تواند دستورها را
کپی کند و در ترمینال سرور اجرا کند. نتیجهٔ نهایی شامل این بخش‌ها است:

- بک‌اند بوکینو؛
- دیتابیس PostgreSQL؛
- فضای دائمی برای جلدها و فایل‌های رمزگذاری‌شدهٔ کتاب؛
- دامنه و گواهی امن HTTPS؛
- بکاپ و روش به‌روزرسانی.

در این راهنما فرض شده است یک سرور مجازی لینوکسی (VPS) با Ubuntu یا Debian دارید.
اگر هاست شما فقط «هاست اشتراکی» با پنل cPanel یا DirectAdmin است و اجازهٔ اجرای
Docker نمی‌دهد، این روش روی آن قابل اجرا نیست. در آن حالت باید VPS یا سرویس
میزبانی Docker تهیه کنید.

> **هشدار بسیار مهم:** مقدار `BOOK_KEK_BASE64` کلید اصلی حفاظت از کتاب‌ها است.
> اگر این مقدار گم یا عوض شود، کتاب‌هایی که قبلاً آپلود شده‌اند دیگر باز نمی‌شوند.
> آن را در Password Manager و یک بکاپ امن جداگانه نگه دارید.

## قبل از شروع چه چیزهایی لازم است؟

موارد زیر را آماده کنید:

1. یک VPS با حداقل ۱ گیگابایت RAM و فضای کافی برای کتاب‌ها؛
2. Ubuntu یا Debian و دسترسی SSH؛
3. یک دامنه یا زیردامنه، مثلاً `api.example.com`؛
4. فایل‌های پروژه یا آدرس مخزن Git پروژه؛
5. Docker، Docker Compose و Git روی سرور؛
6. یک Password Manager برای نگهداری رمزها و کلیدها.

در تمام دستورهای این راهنما، این عبارت‌ها نمونه هستند و باید جایگزین شوند:

| عبارت نمونه | باید با چه چیزی عوض شود؟ |
| --- | --- |
| `api.example.com` | دامنهٔ واقعی API |
| `admin.example.com` | دامنهٔ واقعی پنل مدیریت |
| `YOUR_REPOSITORY_URL` | آدرس مخزن Git پروژه |
| `YOUR_SERVER_IP` | آی‌پی عمومی سرور |

## مرحلهٔ ۱: اتصال به سرور

در macOS یا Linux برنامهٔ Terminal را باز کنید. در Windows می‌توانید از
PowerShell استفاده کنید. سپس این دستور را اجرا کنید:

```sh
ssh root@YOUR_SERVER_IP
```

اگر شرکت میزبان نام کاربری دیگری داده است، `root` را با همان نام عوض کنید.
بار اول ممکن است سؤال `Are you sure you want to continue connecting?` نمایش
داده شود؛ پس از تطبیق اثر انگشت سرور با اطلاعات شرکت میزبان، `yes` وارد کنید.

بعد از ورود، نصب بودن ابزارها را بررسی کنید:

```sh
docker --version
docker compose version
git --version
openssl version
```

هر چهار دستور باید شمارهٔ نسخه نشان دهند. اگر Docker یا Compose نصب نیست، از
شرکت میزبان بخواهید Docker Engine و Docker Compose Plugin را نصب کند. ادامهٔ
کار بدون این دو ابزار ممکن نیست.

## مرحلهٔ ۲: اتصال دامنه به سرور

در پنل شرکتی که DNS دامنه را مدیریت می‌کند، یک رکورد بسازید:

| نوع | Name یا Host | Value یا Destination |
| --- | --- | --- |
| `A` | `api` | آی‌پی عمومی VPS |

اگر دامنهٔ شما `example.com` باشد، نتیجه `api.example.com` می‌شود. رکورد `AAAA`
را فقط زمانی اضافه کنید که شرکت میزبان IPv6 فعال و قابل دسترس داده باشد.

در فایروال پنل هاست و فایروال خود سرور، فقط این پورت‌های ورودی لازم‌اند:

- پورت `22` برای SSH؛
- پورت `80` برای صدور گواهی HTTPS؛
- پورت `443` برای HTTPS.

پورت دیتابیس (`5432`) و پورت داخلی بک‌اند (`8000`) را عمومی نکنید.

برای بررسی DNS، روی کامپیوتر خود اجرا کنید:

```sh
nslookup api.example.com
```

آی‌پی نمایش‌داده‌شده باید با آی‌پی VPS یکی باشد. انتشار تغییر DNS ممکن است کمی
زمان ببرد.

## مرحلهٔ ۳: انتقال پروژه به سرور

پس از ورود SSH، پوشهٔ برنامه را بسازید:

```sh
mkdir -p /opt/protected-book
cd /opt/protected-book
```

اگر پروژه در Git قرار دارد، آن را دریافت کنید:

```sh
git clone YOUR_REPOSITORY_URL .
```

نقطهٔ آخر دستور مهم است. پس از پایان، این فایل‌ها باید در پوشه دیده شوند:

```sh
ls
```

در خروجی باید حداقل `Dockerfile`، پوشهٔ `src`، پوشهٔ `migrations` و فایل
`alembic.ini` دیده شود. اگر مخزن اصلی شامل چند پروژه است و بک‌اند در زیرپوشهٔ
`backend` قرار دارد، وارد همان پوشه شوید:

```sh
cd backend
```

از این مرحله به بعد، تمام دستورها باید در پوشه‌ای اجرا شوند که `Dockerfile` در
آن قرار دارد.

## مرحلهٔ ۴: ساخت رمزها و تنظیمات تولید

سه مقدار تصادفی بسازید:

```sh
openssl rand -hex 32
openssl rand -hex 32
openssl rand -base64 32
```

هر دستور یک خروجی متفاوت می‌دهد. آن‌ها را موقتاً در Password Manager ذخیره
کنید:

1. خروجی اول: رمز دیتابیس، یعنی `POSTGRES_PASSWORD`؛
2. خروجی دوم: کلید نشست‌ها، یعنی `JWT_SECRET`؛
3. خروجی سوم: کلید اصلی کتاب‌ها، یعنی `BOOK_KEK_BASE64`.

حالا فایل تنظیمات را باز کنید:

```sh
nano .env
```

متن زیر را وارد کنید و همهٔ عبارت‌های نمونه را جایگزین کنید:

```dotenv
APP_ENV=production
POSTGRES_DB=book_reader
POSTGRES_USER=book_reader
POSTGRES_PASSWORD=خروجی_اول_openssl
DATABASE_URL=postgresql+psycopg://book_reader:خروجی_اول_openssl@db:5432/book_reader
JWT_SECRET=خروجی_دوم_openssl
BOOK_KEK_BASE64=خروجی_سوم_openssl
STORAGE_ROOT=/data/storage
ADMIN_ORIGINS=https://admin.example.com
COOKIE_SECURE=true
MAX_PDF_BYTES=209715200
MAX_COVER_BYTES=2097152
API_DOMAIN=api.example.com
```

در nano با `Ctrl+O`، سپس Enter فایل را ذخیره کنید و با `Ctrl+X` خارج شوید.
دسترسی فایل را محدود کنید:

```sh
chmod 600 .env
```

نکات مهم:

- رمز داخل `DATABASE_URL` باید دقیقاً همان `POSTGRES_PASSWORD` باشد.
- نام میزبان دیتابیس در این روش باید `db` باشد؛ `localhost` اشتباه است.
- انتهای `ADMIN_ORIGINS` علامت `/` نگذارید.
- اگر چند پنل مدیریت دارید، آدرس‌ها را با ویرگول جدا کنید.
- فایل `.env` را در Git، پیام‌رسان یا ایمیل قرار ندهید.

برای بررسی طول کلید کتاب، این دستور باید عدد `32` را چاپ کند:

```sh
grep '^BOOK_KEK_BASE64=' .env | cut -d= -f2- | base64 -d | wc -c
```

## مرحلهٔ ۵: ساخت فایل اجرای سرویس‌ها

فایل Docker Compose تولید را باز کنید:

```sh
nano compose.production.yaml
```

این متن را عیناً در آن قرار دهید:

```yaml
services:
  db:
    image: postgres:17-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 20

  api:
    build: .
    restart: unless-stopped
    env_file: .env
    volumes:
      - protected_storage:/data/storage
    depends_on:
      db:
        condition: service_healthy

  proxy:
    image: caddy:2-alpine
    restart: unless-stopped
    environment:
      API_DOMAIN: ${API_DOMAIN}
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - api

volumes:
  postgres_data:
    name: protected_book_postgres
  protected_storage:
    name: protected_book_storage
  caddy_data:
    name: protected_book_caddy_data
  caddy_config:
    name: protected_book_caddy_config
```

فایل را ذخیره کنید و سپس فایل تنظیم HTTPS را بسازید:

```sh
nano Caddyfile
```

این متن را وارد کنید:

```caddyfile
{$API_DOMAIN} {
    encode zstd gzip
    request_body {
        max_size 220MB
    }
    reverse_proxy api:8000
}
```

فایل را ذخیره کنید. در این ساختار فقط Caddy به اینترنت متصل است؛ دیتابیس و
بک‌اند در شبکهٔ خصوصی Docker باقی می‌مانند.

## مرحلهٔ ۶: بررسی تنظیمات و اجرای اولیه

ابتدا صحت فایل‌ها را بدون اجرای سرویس بررسی کنید:

```sh
docker compose --env-file .env -f compose.production.yaml config --quiet
```

اگر هیچ پیامی نمایش داده نشد، تنظیمات معتبر است. سپس بک‌اند را بسازید:

```sh
docker compose --env-file .env -f compose.production.yaml build api
```

آزمون‌های پروژه را اجرا کنید:

```sh
docker compose --env-file .env -f compose.production.yaml run --rm --no-deps api pytest
docker compose --env-file .env -f compose.production.yaml run --rm --no-deps api ruff check src tests
```

در آزمون اول باید عبارت `passed` و در آزمون دوم `All checks passed` دیده شود.
حالا سرویس‌ها را روشن کنید:

```sh
docker compose --env-file .env -f compose.production.yaml up -d --build
```

وضعیت را ببینید:

```sh
docker compose --env-file .env -f compose.production.yaml ps
```

سرویس‌های `db`، `api` و `proxy` باید در وضعیت `Up` یا `healthy` باشند. راه‌اندازی
اول ممکن است چند دقیقه طول بکشد؛ Caddy نیز در همین زمان گواهی HTTPS می‌گیرد.

برای دیدن گزارش شروع برنامه:

```sh
docker compose --env-file .env -f compose.production.yaml logs --tail=100 api proxy
```

## مرحلهٔ ۷: اطمینان از کارکرد بک‌اند و دیتابیس

ابتدا خود API و HTTPS را بررسی کنید:

```sh
curl --fail --silent --show-error https://api.example.com/health
```

پاسخ درست این است:

```json
{"status":"ok"}
```

این آدرس فقط روشن بودن برنامه را بررسی می‌کند. برای اطمینان از اتصال دیتابیس،
این دستور را هم اجرا کنید:

```sh
curl --fail --silent --show-error https://api.example.com/api/v1/auth/status
```

قبل از ساخت مدیر اول، پاسخ درست شبیه این است:

```json
{"hasAdmin":false,"authenticated":false,"username":null}
```

مهاجرت‌های دیتابیس را نیز بررسی کنید:

```sh
docker compose --env-file .env -f compose.production.yaml exec api alembic current
```

در خروجی باید عبارت `(head)` دیده شود. برای بررسی مستقیم PostgreSQL:

```sh
docker compose --env-file .env -f compose.production.yaml exec db psql -U book_reader -d book_reader -c 'SELECT count(*) FROM users;'
```

اگر یک عدد برگردد، دیتابیس آماده است.

## مرحلهٔ ۸: ساخت اولین مدیر

این کار فقط یک بار و تا زمانی که هیچ مدیر دیگری وجود ندارد انجام می‌شود. یک نام
کاربری و رمز طولانی انتخاب کنید و دستور زیر را پس از جایگزینی دامنه و رمز اجرا
کنید:

```sh
curl --fail-with-body -c admin-cookie.txt \
  -H 'Content-Type: application/json' \
  -d '{"username":"site-admin","password":"یک_رمز_طولانی_و_غیرتکراری"}' \
  https://api.example.com/api/v1/auth/bootstrap-admin
```

سپس دسترسی مدیر را آزمایش کنید:

```sh
curl --fail --silent --show-error -b admin-cookie.txt https://api.example.com/api/v1/admin/snapshot
```

فایل موقت نشست را حذف کنید:

```sh
rm admin-cookie.txt
```

این فایل فقط یک نشست موقت بود و حذف آن، حساب مدیر را پاک نمی‌کند. اجرای دوبارهٔ
دستور ساخت مدیر باید خطای `409` بدهد؛ این یعنی مسیر ساخت مدیر اولیه بسته شده است.

## مرحلهٔ ۹: اتصال پنل مدیریت و اپ Android

هنگام ساخت پنل مدیریت، آدرس API باید این مقدار باشد:

```text
https://api.example.com/api/v1/
```

همین دامنه باید در `ADMIN_ORIGINS` ثبت شده باشد. برای اپ Android نیز مقدار
`API_BASE_URL` باید به همین آدرس HTTPS اشاره کند. پس از اتصال:

1. در پنل مدیریت وارد شوید؛
2. یک جلد و PDF کوچک آزمایشی آپلود کنید؛
3. کتاب را منتشر کنید؛
4. در اپ Android وارد حساب کاربر شوید؛
5. کتاب را دانلود و باز کنید؛
6. سرویس‌ها را یک بار ری‌استارت کنید و دوباره کتاب را بررسی کنید:

```sh
docker compose --env-file .env -f compose.production.yaml restart
```

فایل PDF اصلی از بک‌اند ارائه نمی‌شود. بک‌اند نسخهٔ رمزگذاری‌شدهٔ `.brc` را در
فضای دائمی نگه می‌دارد و کلید خواندن کتاب برای دستگاه ثبت‌شده محافظت می‌شود.

## مرحلهٔ ۱۰: بکاپ ضروری

یک بکاپ قابل استفاده سه جزء دارد و هر سه باید متعلق به یک زمان و یک سرور باشند:

1. خروجی دیتابیس PostgreSQL؛
2. تمام فایل‌های فضای `/data/storage`؛
3. فایل `.env`، به‌خصوص `BOOK_KEK_BASE64`.

پوشهٔ بکاپ را بسازید:

```sh
install -d -m 700 /var/backups/protected-book
```

از دیتابیس و فایل‌ها بکاپ بگیرید:

```sh
docker compose --env-file .env -f compose.production.yaml exec -T db \
  pg_dump -U book_reader -d book_reader -Fc \
  > /var/backups/protected-book/database.dump

docker compose --env-file .env -f compose.production.yaml exec -T api \
  tar -C /data/storage -czf - . \
  > /var/backups/protected-book/storage.tar.gz

cp .env /var/backups/protected-book/environment.env
chmod 600 /var/backups/protected-book/*
```

این پوشه را به یک محل رمزگذاری‌شده خارج از VPS نیز منتقل کنید. بکاپی که فقط روی
همان سرور باشد، در خرابی یا حذف سرور از بین می‌رود. دست‌کم ماهی یک بار بازگردانی
بکاپ را روی یک سرور آزمایشی امتحان کنید.

> برای بازگردانی کتاب‌ها باید دقیقاً همان دیتابیس، فایل‌های storage و
> `BOOK_KEK_BASE64` با هم استفاده شوند. این سه جزء را با نسخه‌های متعلق به
> زمان‌های متفاوت مخلوط نکنید.

## مرحلهٔ ۱۱: به‌روزرسانی برنامه

پیش از هر به‌روزرسانی، بکاپ مرحلهٔ قبل را بگیرید. سپس اجرا کنید:

```sh
cd /opt/protected-book
git pull --ff-only
docker compose --env-file .env -f compose.production.yaml build api
docker compose --env-file .env -f compose.production.yaml up -d
docker compose --env-file .env -f compose.production.yaml ps
curl --fail https://api.example.com/health
curl --fail https://api.example.com/api/v1/auth/status
```

اگر `Dockerfile` در زیرپوشهٔ `backend` است، پس از دستور `cd` وارد آن زیرپوشه
شوید. هنگام شروع، بک‌اند به‌صورت خودکار تغییرات لازم دیتابیس را اجرا می‌کند.

## مرحلهٔ ۱۲: عیب‌یابی ساده

در بیشتر خطاها، ابتدا این چهار دستور را اجرا کنید:

```sh
docker compose --env-file .env -f compose.production.yaml ps
docker compose --env-file .env -f compose.production.yaml logs --tail=200 api
docker compose --env-file .env -f compose.production.yaml logs --tail=200 db
docker compose --env-file .env -f compose.production.yaml logs --tail=200 proxy
```

خطاهای رایج:

- **بک‌اند مرتب خاموش و روشن می‌شود:** `JWT_SECRET` کوتاه یا تکراری است،
  `BOOK_KEK_BASE64` معتبر نیست، دیتابیس در دسترس نیست یا مهاجرت دیتابیس خطا دارد.
- **اتصال دیتابیس رد می‌شود:** در `DATABASE_URL` نام میزبان باید `db` باشد و رمز
  باید با `POSTGRES_PASSWORD` یکسان باشد.
- **HTTPS فعال نمی‌شود:** DNS، باز بودن پورت‌های ۸۰ و ۴۴۳ و اشغال نبودن آن‌ها را
  بررسی کنید.
- **ورود مدیر موفق است ولی بعد خطای 401 می‌آید:** API و پنل باید HTTPS باشند؛
  `COOKIE_SECURE=true` باشد و آدرس پنل در `ADMIN_ORIGINS` دقیق ثبت شده باشد.
- **مرورگر خطای CORS می‌دهد:** scheme، دامنه و پورت `ADMIN_ORIGINS` باید دقیقاً
  با آدرس پنل یکی باشد و در انتهای آن `/` نباشد.
- **آپلود خطای 413 می‌دهد:** فضای دیسک و محدودیت‌های `MAX_PDF_BYTES`،
  `MAX_COVER_BYTES` و `max_size` در Caddyfile را بررسی کنید.
- **فایل‌ها پس از استقرار مجدد ناپدید می‌شوند:** volume با نام
  `protected_book_storage` باید به `/data/storage` متصل باشد.
- **کتاب‌های قدیمی باز نمی‌شوند:** مقدار اصلی `BOOK_KEK_BASE64` را از بکاپ
  برگردانید. بدون آن بازیابی کلید کتاب‌ها ممکن نیست.

## چک‌لیست نهایی

- [ ] دامنه به آی‌پی درست اشاره می‌کند.
- [ ] فقط پورت‌های ۲۲، ۸۰ و ۴۴۳ عمومی‌اند.
- [ ] دیتابیس و پورت ۸۰۰۰ مستقیماً از اینترنت قابل دسترس نیستند.
- [ ] `APP_ENV=production` و `COOKIE_SECURE=true` تنظیم شده‌اند.
- [ ] آدرس `ADMIN_ORIGINS` دقیق است.
- [ ] هر سه رمز تولید منحصربه‌فرد دارند و در Password Manager ذخیره شده‌اند.
- [ ] از `BOOK_KEK_BASE64` یک نسخهٔ امن خارج از VPS وجود دارد.
- [ ] هر سه سرویس `db`، `api` و `proxy` روشن‌اند.
- [ ] هر دو آدرس `/health` و `/api/v1/auth/status` پاسخ `200` می‌دهند.
- [ ] خروجی `alembic current` شامل `(head)` است.
- [ ] ورود مدیر، آپلود PDF، انتشار و باز شدن کتاب در Android آزمایش شده است.
- [ ] بکاپ دیتابیس، storage و `.env` در محل دیگری نگهداری می‌شود.


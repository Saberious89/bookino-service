# Beginner’s guide to deploying the Bookino backend and database

This guide is written for a non-programmer who can copy commands into a server
terminal. When finished, you will have:

- the Bookino backend API;
- a PostgreSQL database;
- persistent storage for covers and encrypted books;
- a domain protected by HTTPS;
- a backup and update procedure.

This guide assumes you have a Linux virtual private server (VPS) running Ubuntu
or Debian. A shared cPanel or DirectAdmin hosting account normally cannot run
this setup because it requires Docker. If your host does not support Docker,
buy a VPS or a managed Docker service instead.

> **Critical:** `BOOK_KEK_BASE64` is the master key that protects all uploaded
> books. If it is lost or changed, previously uploaded books cannot be opened.
> Store it in a password manager and in a separate, secure backup.

## What you need before starting

Prepare the following:

1. A VPS with at least 1 GB RAM and enough disk space for the books.
2. Ubuntu or Debian with SSH access.
3. A domain or subdomain, such as `api.example.com`.
4. The Git repository URL or a copy of the backend project.
5. Docker, Docker Compose, Git, and OpenSSL on the server.
6. A password manager for the database password and encryption keys.

Replace these examples everywhere in the guide:

| Example | Replace it with |
| --- | --- |
| `api.example.com` | The real API domain |
| `admin.example.com` | The real web admin domain |
| `YOUR_REPOSITORY_URL` | The Git repository URL |
| `YOUR_SERVER_IP` | The VPS public IP address |

## Step 1: Connect to the server

Open Terminal on macOS or Linux, or PowerShell on Windows. Run:

```sh
ssh root@YOUR_SERVER_IP
```

If your hosting company gave you a different SSH username, replace `root` with
that username. On the first connection, SSH may ask whether you want to continue.
Check the server fingerprint against the value supplied by your host, then enter
`yes`.

Check that the required programs are installed:

```sh
docker --version
docker compose version
git --version
openssl version
```

All four commands should print a version number. If Docker or Docker Compose is
missing, ask your hosting provider to install Docker Engine and the Docker
Compose plugin. Do not continue until both commands work.

## Step 2: Point the domain to the server

Open the DNS panel for your domain and create this record:

| Type | Name or Host | Value or Destination |
| --- | --- | --- |
| `A` | `api` | The public IP address of the VPS |

For the domain `example.com`, this creates `api.example.com`. Add an `AAAA`
record only when your VPS has working public IPv6.

Allow these incoming TCP ports in both the hosting provider’s firewall and the
server firewall:

- port `22` for SSH;
- port `80` for HTTPS certificate validation;
- port `443` for HTTPS.

Do not expose PostgreSQL port `5432` or the internal API port `8000` publicly.

Check the DNS result from your own computer:

```sh
nslookup api.example.com
```

The result should contain the VPS IP address. DNS changes may take some time to
become visible.

## Step 3: Copy the project to the server

After connecting through SSH, create the application directory:

```sh
mkdir -p /opt/protected-book
cd /opt/protected-book
```

If the project is stored in Git, download it:

```sh
git clone YOUR_REPOSITORY_URL .
```

The final dot is required. Check the downloaded files:

```sh
ls
```

You should see at least `Dockerfile`, `src`, `migrations`, and `alembic.ini`. If
the repository contains several projects and the backend is inside a `backend`
directory, enter that directory:

```sh
cd backend
```

Run every remaining command from the directory that contains `Dockerfile`.

## Step 4: Generate secrets and production settings

Generate three random values:

```sh
openssl rand -hex 32
openssl rand -hex 32
openssl rand -base64 32
```

Each command prints a different value. Save them temporarily in your password
manager:

1. First value: database password, named `POSTGRES_PASSWORD`.
2. Second value: session signing secret, named `JWT_SECRET`.
3. Third value: book master key, named `BOOK_KEK_BASE64`.

Open the environment file:

```sh
nano .env
```

Paste the following text and replace every example value:

```dotenv
APP_ENV=production
POSTGRES_DB=book_reader
POSTGRES_USER=book_reader
POSTGRES_PASSWORD=PASTE_THE_FIRST_OPENSSL_VALUE
DATABASE_URL=postgresql+psycopg://book_reader:PASTE_THE_FIRST_OPENSSL_VALUE@db:5432/book_reader
JWT_SECRET=PASTE_THE_SECOND_OPENSSL_VALUE
BOOK_KEK_BASE64=PASTE_THE_THIRD_OPENSSL_VALUE
STORAGE_ROOT=/data/storage
ADMIN_ORIGINS=https://admin.example.com
COOKIE_SECURE=true
MAX_PDF_BYTES=209715200
MAX_COVER_BYTES=2097152
API_DOMAIN=api.example.com
```

In nano, press `Ctrl+O`, then Enter to save. Press `Ctrl+X` to close it. Protect
the file so only its owner can read it:

```sh
chmod 600 .env
```

Check these details carefully:

- The password inside `DATABASE_URL` must exactly match `POSTGRES_PASSWORD`.
- The database hostname must be `db`, not `localhost`.
- Do not add a trailing `/` to `ADMIN_ORIGINS`.
- Separate multiple admin origins with commas.
- Never place `.env` in Git, email, or a messaging application.

Verify that the book key decodes to exactly 32 bytes:

```sh
grep '^BOOK_KEK_BASE64=' .env | cut -d= -f2- | base64 -d | wc -c
```

The command must print `32`.

## Step 5: Create the production service file

Open the production Docker Compose file:

```sh
nano compose.production.yaml
```

Paste this content exactly:

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

Save the file. Then create the HTTPS proxy configuration:

```sh
nano Caddyfile
```

Paste this content:

```caddyfile
{$API_DOMAIN} {
    encode zstd gzip
    request_body {
        max_size 220MB
    }
    reverse_proxy api:8000
}
```

Save the file. With this configuration, only Caddy is exposed to the internet.
PostgreSQL and the backend remain inside Docker’s private network.

## Step 6: Validate and start the deployment

Check the configuration before starting anything:

```sh
docker compose --env-file .env -f compose.production.yaml config --quiet
```

No output means the configuration is valid. Build the backend image:

```sh
docker compose --env-file .env -f compose.production.yaml build api
```

Run the project checks:

```sh
docker compose --env-file .env -f compose.production.yaml run --rm --no-deps api pytest
docker compose --env-file .env -f compose.production.yaml run --rm --no-deps api ruff check src tests
```

The first command should report `passed`. The second should report
`All checks passed`. Start the services:

```sh
docker compose --env-file .env -f compose.production.yaml up -d --build
```

Check their status:

```sh
docker compose --env-file .env -f compose.production.yaml ps
```

The `db`, `api`, and `proxy` services should be `Up` or `healthy`. The first
startup may take several minutes while images are downloaded and Caddy obtains
the HTTPS certificate.

View the startup logs:

```sh
docker compose --env-file .env -f compose.production.yaml logs --tail=100 api proxy
```

## Step 7: Verify the API and database

Check the API and HTTPS:

```sh
curl --fail --silent --show-error https://api.example.com/health
```

The expected response is:

```json
{"status":"ok"}
```

The health endpoint only checks that the API process responds. Use the following
database-backed endpoint to verify the database connection:

```sh
curl --fail --silent --show-error https://api.example.com/api/v1/auth/status
```

Before creating the first administrator, the expected response is:

```json
{"hasAdmin":false,"authenticated":false,"username":null}
```

Check the database migrations:

```sh
docker compose --env-file .env -f compose.production.yaml exec api alembic current
```

The output must contain `(head)`. Check PostgreSQL directly:

```sh
docker compose --env-file .env -f compose.production.yaml exec db psql -U book_reader -d book_reader -c 'SELECT count(*) FROM users;'
```

If it returns a number, PostgreSQL is ready.

## Step 8: Create the first administrator

This operation works only once, while no administrator exists. Choose a unique
username and a long password, then replace the examples in this command:

```sh
curl --fail-with-body -c admin-cookie.txt \
  -H 'Content-Type: application/json' \
  -d '{"username":"site-admin","password":"REPLACE_WITH_A_LONG_UNIQUE_PASSWORD"}' \
  https://api.example.com/api/v1/auth/bootstrap-admin
```

Test the new administrator session:

```sh
curl --fail --silent --show-error -b admin-cookie.txt https://api.example.com/api/v1/admin/snapshot
```

Remove the temporary session file:

```sh
rm admin-cookie.txt
```

This removes only the temporary login session, not the administrator account. A
second bootstrap request should return HTTP `409`, confirming that initial setup
is closed.

## Step 9: Connect the web admin and Android application

Build the web admin with this API URL:

```text
https://api.example.com/api/v1/
```

The web admin’s domain must exactly match `ADMIN_ORIGINS`. Build the Android app
with `API_BASE_URL` pointing to the same HTTPS API address. Then perform this
end-to-end check:

1. Sign in to the web admin.
2. Upload a small test cover and PDF.
3. Publish the book.
4. Sign in as a reader in the Android app.
5. Download and open the book.
6. Restart the server services and confirm that the book still exists:

```sh
docker compose --env-file .env -f compose.production.yaml restart
```

The backend does not serve the original PDF. It stores and downloads an
encrypted `.brc` container, and protects its reading key for the registered
Android device.

## Step 10: Create essential backups

A usable backup has three matching parts:

1. A PostgreSQL database dump.
2. All files under `/data/storage`.
3. The `.env` file, especially `BOOK_KEK_BASE64`.

Create a protected backup directory:

```sh
install -d -m 700 /var/backups/protected-book
```

Back up the database, protected storage, and environment:

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

Copy these backups to a separate encrypted location outside the VPS. A backup
stored only on the same VPS will disappear if the server or account is lost.
Test restoration on a separate test server at least once a month.

> Restore the matching database, storage archive, and `BOOK_KEK_BASE64`
> together. Do not combine these three items from different backup dates.

## Step 11: Update the application

Create a complete backup before every update. Then run:

```sh
cd /opt/protected-book
git pull --ff-only
docker compose --env-file .env -f compose.production.yaml build api
docker compose --env-file .env -f compose.production.yaml up -d
docker compose --env-file .env -f compose.production.yaml ps
curl --fail https://api.example.com/health
curl --fail https://api.example.com/api/v1/auth/status
```

If `Dockerfile` is inside the `backend` directory, enter that directory after
`cd /opt/protected-book`. The backend automatically applies pending database
migrations before it starts.

## Step 12: Basic troubleshooting

Start with these four commands whenever something is wrong:

```sh
docker compose --env-file .env -f compose.production.yaml ps
docker compose --env-file .env -f compose.production.yaml logs --tail=200 api
docker compose --env-file .env -f compose.production.yaml logs --tail=200 db
docker compose --env-file .env -f compose.production.yaml logs --tail=200 proxy
```

Common problems:

- **The API keeps restarting:** Check for a short or invalid `JWT_SECRET`, a
  missing or invalid `BOOK_KEK_BASE64`, an unreachable database, or a failed
  migration.
- **Database connection refused:** `DATABASE_URL` must use hostname `db`; its
  username, password, and database must match the `POSTGRES_*` values.
- **HTTPS does not start:** Check DNS, ports 80 and 443, and whether another
  program is already using those ports.
- **Admin login succeeds but later requests return 401:** Use HTTPS, set
  `COOKIE_SECURE=true`, and ensure the exact admin address is in `ADMIN_ORIGINS`.
- **The browser reports a CORS error:** The scheme, hostname, and port in
  `ADMIN_ORIGINS` must exactly match the web admin, without a trailing slash.
- **Uploads return 413:** Check free disk space and compare `MAX_PDF_BYTES`,
  `MAX_COVER_BYTES`, and `max_size` in `Caddyfile`.
- **Uploads disappear after redeployment:** Confirm that the
  `protected_book_storage` volume is mounted at `/data/storage`.
- **Old books no longer open:** Restore the original `BOOK_KEK_BASE64`. The book
  keys cannot be recovered without it.

## Final checklist

- [ ] The API domain resolves to the correct VPS IP address.
- [ ] Only ports 22, 80, and 443 are public.
- [ ] PostgreSQL and port 8000 are not directly accessible from the internet.
- [ ] `APP_ENV=production` and `COOKIE_SECURE=true` are set.
- [ ] `ADMIN_ORIGINS` exactly matches the web admin address.
- [ ] All three generated secrets are unique and stored in a password manager.
- [ ] `BOOK_KEK_BASE64` has a secure copy outside the VPS.
- [ ] The `db`, `api`, and `proxy` services are running.
- [ ] `/health` and `/api/v1/auth/status` both return HTTP 200.
- [ ] `alembic current` contains `(head)`.
- [ ] Admin login, PDF upload, publishing, and Android reading have been tested.
- [ ] The database, protected storage, and `.env` are backed up off the server.


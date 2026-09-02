# Production deployment and verification

This guide deploys the Protected Book Backend to a single Linux host with Docker
Compose, PostgreSQL, persistent encrypted-book storage, and automatic HTTPS. It is
written for a typical VPS (for example, Ubuntu or Debian) with a public IP address.

The repository's `compose.yaml` is suitable for local development. Do not use it
unchanged in production: it contains development database credentials and publishes
the API directly on port 8000 without TLS.

## 1. Understand what is being deployed

The production stack has three services:

- `api`: FastAPI/Uvicorn, built from this repository's `Dockerfile`.
- `db`: PostgreSQL 17, stored in a persistent Docker volume.
- `proxy`: Caddy, which obtains and renews the TLS certificate and forwards HTTPS
  requests to the API.

The API runs Alembic migrations before it starts. Uploaded covers and encrypted
`.brc` book objects are stored separately from PostgreSQL in another persistent
volume.

Two secrets are especially important:

- `JWT_SECRET` signs admin sessions. Rotating it logs out existing admins.
- `BOOK_KEK_BASE64` wraps the per-book encryption keys. If it is lost or changed,
  previously uploaded books cannot be decrypted. Back it up securely.

## 2. Prepare the host and DNS

Use a host with at least 1 GB RAM, enough disk for PostgreSQL plus all uploaded
books and backups, and Docker Engine with the Docker Compose plugin installed.
Confirm the installation:

```sh
docker --version
docker compose version
git --version
```

Choose an API hostname, such as `api.example.com`, and create an `A` record pointing
it to the host's public IPv4 address. Add an `AAAA` record only if IPv6 is configured
and reachable on the host.

Allow inbound TCP ports 22 (SSH), 80 (HTTP certificate validation), and 443 (HTTPS)
in both the hosting-provider firewall and the host firewall. Do not expose ports
5432 or 8000 publicly.

For cookie authentication to work reliably, host the web admin on another HTTPS
subdomain of the same parent domain, such as `admin.example.com`. The configured
admin origin must exactly match its scheme, hostname, and port.

## 3. Copy the project to the host

The following examples use `/opt/protected-book`:

```sh
sudo mkdir -p /opt/protected-book
sudo chown "$USER":"$USER" /opt/protected-book
git clone YOUR_REPOSITORY_URL /opt/protected-book
cd /opt/protected-book
```

For a private repository, configure a read-only deploy key or copy a release archive
to that directory instead. Keep the `.env` file and backup files out of Git.

## 4. Create production secrets and environment settings

Generate the three required random values and store them temporarily in a password
manager:

```sh
openssl rand -hex 32
openssl rand -hex 32
openssl rand -base64 32
```

Use the first result as `POSTGRES_PASSWORD`, the second as `JWT_SECRET`, and the
third as `BOOK_KEK_BASE64`. Hex is used for the database password so it can be placed
in `DATABASE_URL` without URL escaping.

Create `/opt/protected-book/.env` with permissions `600`:

```dotenv
APP_ENV=production
POSTGRES_DB=book_reader
POSTGRES_USER=book_reader
POSTGRES_PASSWORD=PASTE_THE_FIRST_HEX_VALUE
DATABASE_URL=postgresql+psycopg://book_reader:PASTE_THE_FIRST_HEX_VALUE@db:5432/book_reader
JWT_SECRET=PASTE_THE_SECOND_HEX_VALUE
BOOK_KEK_BASE64=PASTE_THE_BASE64_VALUE
STORAGE_ROOT=/data/storage
ADMIN_ORIGINS=https://admin.example.com
COOKIE_SECURE=true
MAX_PDF_BYTES=209715200
MAX_COVER_BYTES=2097152
API_DOMAIN=api.example.com
```

Then protect it:

```sh
chmod 600 .env
```

Important checks:

- `APP_ENV` must be `production`.
- The password embedded in `DATABASE_URL` must equal `POSTGRES_PASSWORD`.
- The database hostname in `DATABASE_URL` must be `db`, not `localhost`.
- `BOOK_KEK_BASE64` must decode to exactly 32 bytes.
- Do not add a trailing slash to `ADMIN_ORIGINS`.
- Use `COOKIE_SECURE=true` when the public endpoint uses HTTPS.

## 5. Create the production Compose file

Create `/opt/protected-book/compose.production.yaml`:

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

This file does not publish PostgreSQL or Uvicorn to the host. Only Caddy receives
public traffic.

Create `/opt/protected-book/Caddyfile`:

```caddyfile
{$API_DOMAIN} {
    encode zstd gzip
    request_body {
        max_size 220MB
    }
    reverse_proxy api:8000
}
```

The proxy limit is slightly larger than the application's default 200 MiB PDF
limit so multipart form overhead is not rejected first.

## 6. Validate and start the deployment

Render the Compose configuration before starting it. This catches invalid YAML,
missing variables, and interpolation problems:

```sh
docker compose --env-file .env -f compose.production.yaml config --quiet
```

Build the image and run the repository's unit checks before starting it:

```sh
docker compose --env-file .env -f compose.production.yaml build api
docker compose --env-file .env -f compose.production.yaml run --rm --no-deps api pytest
docker compose --env-file .env -f compose.production.yaml run --rm --no-deps api \
  ruff check src tests
```

Then start all services:

```sh
docker compose --env-file .env -f compose.production.yaml up -d --build
```

Watch the first startup:

```sh
docker compose --env-file .env -f compose.production.yaml ps
docker compose --env-file .env -f compose.production.yaml logs -f api proxy
```

The API log should show Alembic reaching revision `0001` and Uvicorn listening on
`0.0.0.0:8000`. Caddy should report a successfully managed certificate. Stop the
live log view with `Ctrl+C`; this does not stop the services.

## 7. Verify every layer

Replace `api.example.com` in the commands below.

### 7.1 Process and TLS check

```sh
curl --fail --silent --show-error https://api.example.com/health
```

Expected response:

```json
{"status":"ok"}
```

This endpoint only confirms that the API process responds; it does not query
PostgreSQL.

Inspect the certificate and redirect:

```sh
curl --head http://api.example.com/health
curl --head https://api.example.com/docs
```

HTTP should redirect to HTTPS, and the HTTPS request should complete without a
certificate warning.

### 7.2 Database and migration check

The auth-status endpoint performs a database query, so it is a better readiness
test than `/health`:

```sh
curl --fail --silent --show-error https://api.example.com/api/v1/auth/status
```

Before the first admin is created, expect:

```json
{"hasAdmin":false,"authenticated":false,"username":null}
```

Also check the migration and database directly on the host:

```sh
docker compose --env-file .env -f compose.production.yaml exec api alembic current
docker compose --env-file .env -f compose.production.yaml exec db \
  psql -U book_reader -d book_reader -c 'SELECT count(*) FROM users;'
```

Alembic should report `0001 (head)`, and the SQL command should return a count.

### 7.3 Bootstrap the first administrator

The bootstrap endpoint works only while no admin exists. Choose a unique username
and a password of 10 to 200 characters:

```sh
curl --fail-with-body -c admin-cookie.txt \
  -H 'Content-Type: application/json' \
  -d '{"username":"site-admin","password":"REPLACE_WITH_A_LONG_PASSWORD"}' \
  https://api.example.com/api/v1/auth/bootstrap-admin
```

The expected HTTP status is `201`. Confirm that the returned session can access an
admin-only endpoint:

```sh
curl --fail --silent --show-error -b admin-cookie.txt \
  https://api.example.com/api/v1/admin/snapshot
```

Delete `admin-cookie.txt` after the check because it contains an active session.
A second bootstrap attempt should return `409`, which confirms that initial setup
is closed.

### 7.4 Browser/admin application check

Configure the Flutter web admin with:

```text
API_BASE_URL=https://api.example.com/api/v1/
```

Open the admin application in a private browser window, sign in, and verify:

1. The browser's Network panel shows no CORS, mixed-content, or certificate errors.
2. `POST /api/v1/auth/login` returns `200` and sets the `book_admin_session` cookie
   with `Secure`, `HttpOnly`, and `SameSite=Lax`.
3. `GET /api/v1/admin/snapshot` returns `200` after login.
4. Upload a small cover and PDF, publish the book, and confirm it appears in
   `GET /api/v1/catalog`.
5. Restart the stack and confirm the uploaded book and cover still exist:

```sh
docker compose --env-file .env -f compose.production.yaml restart
```

## 8. Back up and restore

A usable backup requires all three of the following from the same deployment:

1. A PostgreSQL dump.
2. The complete protected-storage volume.
3. The `.env` secrets, especially `BOOK_KEK_BASE64`.

Create a root-only backup directory, then make database and storage archives:

```sh
sudo install -d -m 700 -o "$USER" -g "$USER" /var/backups/protected-book
docker compose --env-file .env -f compose.production.yaml exec -T db \
  pg_dump -U book_reader -d book_reader -Fc \
  > /var/backups/protected-book/database.dump
docker compose --env-file .env -f compose.production.yaml exec -T api \
  tar -C /data/storage -czf - . \
  > /var/backups/protected-book/storage.tar.gz
cp .env /var/backups/protected-book/environment.env
chmod 600 /var/backups/protected-book/*
```

Copy backups to a separate encrypted location. A backup stored only on the same VPS
does not protect against disk or account loss. Regularly test restoration on a
separate host.

For a planned restore, stop writes, restore PostgreSQL with `pg_restore`, extract
the storage archive into `/data/storage`, restore the matching `.env`, and then
start the API. Do not start the restored API with a different `BOOK_KEK_BASE64`.

## 9. Deploy updates

Before every update, read the release notes and make a database/storage/secret
backup. Then:

```sh
cd /opt/protected-book
git pull --ff-only
docker compose --env-file .env -f compose.production.yaml build api
docker compose --env-file .env -f compose.production.yaml up -d
docker compose --env-file .env -f compose.production.yaml ps
curl --fail https://api.example.com/health
curl --fail https://api.example.com/api/v1/auth/status
```

The API container applies pending migrations before Uvicorn starts. If an update
fails after a migration, changing only the Git revision may not be sufficient;
restore the matching database and storage backup unless the release provides a
tested downgrade migration.

## 10. Monitoring and troubleshooting

Use these commands first:

```sh
docker compose --env-file .env -f compose.production.yaml ps
docker compose --env-file .env -f compose.production.yaml logs --tail=200 api
docker compose --env-file .env -f compose.production.yaml logs --tail=200 db
docker compose --env-file .env -f compose.production.yaml logs --tail=200 proxy
docker system df
```

Common problems:

- **API repeatedly restarts:** check for an invalid/short `JWT_SECRET`, a missing or
  invalid `BOOK_KEK_BASE64`, an unreachable database, or a failed migration.
- **Database connection refused:** ensure `DATABASE_URL` uses host `db` and that its
  username, password, and database match the three `POSTGRES_*` values.
- **Caddy cannot issue a certificate:** verify DNS points to this host, ports 80 and
  443 are reachable, and no other process is using them.
- **Admin login succeeds but subsequent requests return 401:** verify HTTPS is used,
  `COOKIE_SECURE=true`, frontend and API share the same parent site, and the frontend
  sends credentialed requests.
- **Browser reports CORS errors:** make `ADMIN_ORIGINS` exactly match the frontend
  origin. Multiple origins are comma-separated.
- **Uploads return 413:** compare the Caddy request-body limit with `MAX_PDF_BYTES`
  or `MAX_COVER_BYTES`, and confirm the host has sufficient free disk space.
- **Uploads disappear after a rebuild:** confirm the API has the
  `protected_book_storage` volume mounted at `/data/storage`.
- **Old books cannot be opened after secret changes:** restore the original
  `BOOK_KEK_BASE64`; encrypted book keys cannot be recovered without it.

For external monitoring, check both `/health` and `/api/v1/auth/status`. The first
detects process/proxy/TLS failures; the second also detects database failures.

## 11. Production checklist

- [ ] DNS resolves to the correct host.
- [ ] Only SSH, HTTP, and HTTPS are public; PostgreSQL and port 8000 are private.
- [ ] `APP_ENV=production`, `COOKIE_SECURE=true`, and `ADMIN_ORIGINS` is exact.
- [ ] Database, JWT, and book-encryption secrets are unique and securely backed up.
- [ ] `docker compose config --quiet` succeeds.
- [ ] All three containers are running or healthy.
- [ ] HTTPS has a trusted certificate and HTTP redirects to HTTPS.
- [ ] `/health` and `/api/v1/auth/status` return `200`.
- [ ] Alembic reports the head revision.
- [ ] The admin login, upload, publish, catalog, and persistence checks pass.
- [ ] Database, storage, and secret backups exist off-host and restoration is tested.

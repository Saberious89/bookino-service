# Deploy the Protected Book Backend on Runflare

This guide deploys this repository as a Docker service on Runflare, with a
separate managed PostgreSQL database and a persistent disk for encrypted books
and cover images. It is specific to the current `Dockerfile`, FastAPI app, and
environment variables in this repository.

Runflare's public documentation is mostly screenshot-driven and some pages are
several years old, so a portal label may differ slightly. The service shape,
paths, ports, and environment values below come from this repository; links are
provided for every Runflare-specific operation. If the current portal presents a
different networking field, confirm the `80` to `8000` mapping with Runflare
support before going live.

> **Important:** Runflare deploys the API service from the `Dockerfile`; it does
> not use this repository's `compose.yaml` to create PostgreSQL. Create the API
> and PostgreSQL as two separate Runflare deployments in the same project.

## What you will create

- One Runflare project with enough capacity for at least two deployments.
- One PostgreSQL database deployment.
- One Docker service built from this repository's `Dockerfile`.
- One persistent disk mounted at `/data/storage` on the Docker service.
- One public route to the API's container port `8000`.
- Optionally, a custom API domain with HTTPS.

Runflare's project documentation notes that an application plus PostgreSQL uses
two deployments. Its Docker offering builds projects that contain a
`Dockerfile`.

Sources: [Create a Runflare project](https://runflare.com/docs/create-project/),
[Runflare Docker hosting](https://runflare.com/%D9%87%D8%A7%D8%B3%D8%AA-%D8%A7%D8%A8%D8%B1%DB%8C-docker/)

## 1. Check the backend before deploying

Run these commands from the backend repository, not from the parent Flutter
workspace:

```sh
cd /Users/saber/Documents/projects/book_reader_codex/backend
docker build -t protected-book-backend .
docker compose run --rm api pytest
docker compose run --rm api ruff check src tests
```

The repository that Runflare should receive is:

```text
https://github.com/Saberious89/bookino-service.git
```

The current local branch is `develop`. Select the branch that you actually use
for production; do not enable automatic deployment from `develop` unless that is
intentional.

The image starts with this command from the repository's `Dockerfile`:

```sh
alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000
```

This automatically runs pending database migrations before the API starts.

## 2. Create the Runflare project

1. Sign in to the [Runflare portal](https://portal.runflare.com/).
2. Create a new project with a short Latin-character identifier.
3. Select the desired location.
4. Select a plan with at least two deployment slots and enough disk for the API,
   PostgreSQL, and uploaded books.
5. Finish the order and open **Manage project**.

A practical starting point is at least 512 MiB RAM for the API, plus separate
resources for PostgreSQL. Increase API memory if large PDF uploads cause the
container to be terminated.

Source: [Runflare project creation](https://runflare.com/docs/create-project/)

## 3. Create PostgreSQL

1. In the project, choose **Create** and open the **Databases** tab.
2. Create a PostgreSQL deployment.
3. Choose a strong password and allocate database resources.
4. Open the new database's details page and record:
   - internal database hostname;
   - port, normally `5432`;
   - database name;
   - username;
   - password.
5. Keep remote database access disabled unless it is temporarily needed for
   administration. The API should use the internal hostname because both
   deployments are in the same Runflare project.

Runflare's PostgreSQL documentation says internal connections use the database
address shown in the panel; port `5432` can be supplied when a client requires
one.

Source: [Runflare PostgreSQL connections](https://runflare.com/docs/postgres/)

## 4. Create the Docker API service

1. In the same project, choose **Create** and open the **Services** tab.
2. Select the **Docker** application type.
3. Give the service a name such as `bookino-api`.
4. Allocate RAM, CPU, and service disk, then create it.
5. Do not create a second PostgreSQL container and do not try to deploy
   `compose.yaml`; the database from Step 3 replaces the `db` service used for
   local development.

Source: [Create a Runflare service](https://runflare.com/docs/create-service/)

## 5. Add persistent book storage

The API writes covers and encrypted `.brc` book objects beneath
`STORAGE_ROOT`. These files must survive deploys and restarts.

1. Open the project or API service's **Disk management** page.
2. Choose **Add disk**.
3. Attach the disk to `bookino-api`.
4. Set its absolute mount path to:

   ```text
   /data/storage
   ```

5. Size it for the expected encrypted book library, cover images, and growth.
6. Save the disk configuration before uploading any books.

Runflare documents that paths modified after deployment must be backed by a
disk, and that a mounted disk survives service restarts and stops.

Source: [Add a persistent disk to a Runflare service](https://runflare.com/docs/add-disk-to-service/)

## 6. Generate production secrets

Generate these values locally and save them in a password manager:

```sh
openssl rand -hex 32
openssl rand -base64 32
```

- Use the first value for `JWT_SECRET`.
- Use the second value for `BOOK_KEK_BASE64`.

`BOOK_KEK_BASE64` is especially important: it wraps the per-book encryption
keys. If it is lost or changed, previously uploaded books cannot be decrypted.
Back it up separately from Runflare.

## 7. Configure environment variables and secrets

Open the API service's **Environment variables** page. Runflare supports normal
key/value variables, secret-mode variables, and bulk editing. Store at least
`JWT_SECRET`, `BOOK_KEK_BASE64`, and the database password/URL as secrets.

Add these values, replacing every placeholder:

```dotenv
APP_ENV=production
DATABASE_URL=postgresql+psycopg://DB_USER:DB_PASSWORD@INTERNAL_DB_HOST:5432/DB_NAME
JWT_SECRET=PASTE_THE_64_CHARACTER_HEX_VALUE
BOOK_KEK_BASE64=PASTE_THE_BASE64_VALUE
STORAGE_ROOT=/data/storage
ADMIN_ORIGINS=https://admin.example.com
COOKIE_SECURE=true
MAX_PDF_BYTES=209715200
MAX_COVER_BYTES=2097152
```

Checks before saving:

- Use the internal PostgreSQL hostname from Step 3, not `localhost` and not the
  local Compose hostname `db`.
- If the database password contains URL-reserved characters, percent-encode it
  in `DATABASE_URL` or change it to a URL-safe random value.
- `BOOK_KEK_BASE64` must decode to exactly 32 bytes.
- `JWT_SECRET` must contain at least 32 characters in production.
- `ADMIN_ORIGINS` must exactly match the Flutter Web admin origin, including
  `https://` and any nonstandard port, with no trailing slash. Separate multiple
  origins with commas.
- Keep `COOKIE_SECURE=true` when the API and admin are served over HTTPS.

Saving environment changes restarts the service according to Runflare's
documentation.

Sources: [Runflare environment variables](https://runflare.com/docs/setup-environment-variable/),
[Runflare secrets](https://runflare.com/docs/secret/)

## 8. Configure the API port

The container listens on `0.0.0.0:8000`.

1. Open the project's **Networks** page.
2. Add a network for `bookino-api` that forwards incoming HTTP port `80` to
   target/container port `8000`. This mapping applies Runflare's documented
   `80` to application-port example to this repository's Uvicorn port.
3. If the panel asks for network type, select `NodePort` for an internet-facing
   endpoint. `ClusterIP` is internal-only.
4. Do not expose PostgreSQL with `NodePort`.
5. Save the network and note the temporary public address Runflare assigns.

Source: [Runflare network configuration](https://runflare.com/docs/network/)

## 9. Deploy the repository with the Runflare CLI

Install the official CLI on macOS or Linux:

```sh
/bin/bash -c "$(curl -fsSL https://get.runflare.com/install.sh)"
runflare login
```

For the first deployment, run the deploy command from the backend repository
root. This matters because the CLI remembers the first deployment root.

```sh
cd /Users/saber/Documents/projects/book_reader_codex/backend
runflare deploy
```

1. Select the Runflare project created in Step 2.
2. Select the Docker API service created in Step 4.
3. Follow the build logs. The image should install dependencies, run
   `alembic upgrade head`, and start Uvicorn on port `8000`.
4. Enable the service's auto-restart option if Runflare did not restart it after
   the upload.

For later deployments to the remembered service:

```sh
runflare deploy -y
runflare logs -y -f
```

If the first deployment was accidentally run from the parent workspace, clear
the remembered deployment root with `runflare reset`, then redeploy from
`backend`.

Sources: [Install the Runflare CLI](https://runflare.com/docs/get-started/),
[Deploy with the Runflare CLI](https://runflare.com/docs/work-with-cli/cli-deploy/),
[Runflare CLI commands](https://runflare.com/docs/work-with-cli/cli-commands/)

## 10. Verify the temporary Runflare endpoint

Replace `RUNFLARE_API_HOST` with the assigned hostname:

```sh
curl --fail --silent --show-error https://RUNFLARE_API_HOST/health
curl --fail --silent --show-error https://RUNFLARE_API_HOST/api/v1/auth/status
```

Expected health response:

```json
{"status":"ok"}
```

Before the first administrator exists, the database-backed endpoint should
return:

```json
{"hasAdmin":false,"authenticated":false,"username":null}
```

`/health` proves that the API process is reachable. `/api/v1/auth/status` also
proves that Alembic completed and PostgreSQL is reachable.

If either check fails, inspect the logs:

```sh
runflare logs -f
runflare events -f
```

## 11. Attach a custom domain and enable HTTPS

1. In **Domain settings**, add the base domain without `http://` or `www`.
2. Apply the DNS servers or records displayed by Runflare and wait for DNS
   validation.
3. In the domain's details, map a hostname such as `api.example.com` to
   `bookino-api`.
4. Open **SSL settings**, select the hostname, choose Runflare's free
   certificate, and save.
5. Re-run both checks using `https://api.example.com`.

If Cloudflare or ArvanCloud is in front of the domain, Runflare's domain guide
also requires the verification TXT record shown by the portal.

Sources: [Add a domain to Runflare](https://runflare.com/docs/how-to-add-domain/),
[Map a domain to a service](https://runflare.com/docs/add-domain-to-service/),
[Enable SSL on Runflare](https://runflare.com/docs/how-to-work-with-ssl/)

After the final admin URL and API URL are known, update `ADMIN_ORIGINS` to the
exact admin origin and restart the API. Build the Flutter Web admin with:

```text
API_BASE_URL=https://api.example.com/api/v1/
```

For reliable `SameSite=Lax` cookie authentication, host the admin and API on
HTTPS subdomains of the same parent domain, for example `admin.example.com` and
`api.example.com`.

## 12. Create the first administrator

The bootstrap endpoint can create an admin only while no administrator exists:

```sh
curl --fail-with-body -c admin-cookie.txt \
  -H 'Content-Type: application/json' \
  -d '{"username":"site-admin","password":"REPLACE_WITH_A_LONG_PASSWORD"}' \
  https://api.example.com/api/v1/auth/bootstrap-admin
```

Expected status: `201`. Verify the session:

```sh
curl --fail --silent --show-error -b admin-cookie.txt \
  https://api.example.com/api/v1/admin/snapshot
rm admin-cookie.txt
```

A second bootstrap attempt should return `409`.

## 13. Test persistence before going live

1. Sign in through the Flutter Web admin.
2. Upload a small cover and PDF.
3. Publish the book and confirm it appears at `/api/v1/catalog`.
4. Restart `bookino-api` from the Runflare portal or CLI.
5. Confirm the database row, cover, and book still exist.

If database data survives but uploaded files disappear, the disk is not mounted
at `/data/storage`. Fix the disk before accepting production uploads.

## 14. Configure and test backups

A complete recoverable backup consists of all three items:

1. the PostgreSQL database backup;
2. the persistent `/data/storage` disk backup;
3. an external copy of `JWT_SECRET` and, most importantly,
   `BOOK_KEK_BASE64`.

Use Runflare's **Backup list** for PostgreSQL and **Disk backups** for the
persistent disk. Create a manual backup of each, wait for completion, and
download copies to a separate encrypted location. Runflare's portal supports
creating, restoring, and downloading both service/database and disk backups.

Sources: [Create a Runflare backup](https://runflare.com/docs/backup/how-to-generate-backup/),
[Back up a Runflare disk](https://runflare.com/docs/disk-backup/),
[Download a Runflare backup](https://runflare.com/docs/backup/how-to-download-backup/)

Do not treat a provider backup as sufficient until you have tested restoring the
database, disk, and matching encryption secret together.

## 15. Optional: deploy automatically from GitHub

Runflare can connect a service to a repository and optionally pull after every
push.

1. Open `bookino-api` and choose **Connect to GitHub**.
2. Enter `https://github.com/Saberious89/bookino-service.git` and the selected
   production branch.
3. If the repository is private, provide a narrowly scoped token that can read
   the repository. Treat it as a secret and set an expiry/rotation reminder.
4. Select the initial commit to deploy.
5. Enable **Auto pull** only if every push to that branch should deploy.

Runflare's current guide describes repository URL, branch, optional private-repo
token, commit rollback, and automatic pulls.

Source: [Runflare GitHub deployment](https://runflare.com/docs/ci-cd-setup/how-to-add-github/)

## 16. Update procedure

Before an update, create matching database and disk backups and confirm the
encryption secret is stored externally. Then deploy from the backend root:

```sh
cd /Users/saber/Documents/projects/book_reader_codex/backend
runflare deploy -y
runflare logs -y -f
```

After startup, verify:

```sh
curl --fail https://api.example.com/health
curl --fail https://api.example.com/api/v1/auth/status
```

The container runs pending Alembic migrations before it starts serving traffic.
If a release fails after a migration, restoring only an older Git commit may be
insufficient; restore the matching database and disk backup when the release has
no tested downgrade migration.

## Troubleshooting

- **Container repeatedly restarts:** inspect logs for an invalid/short
  `JWT_SECRET`, missing or invalid `BOOK_KEK_BASE64`, failed migration, or bad
  `DATABASE_URL`.
- **Database connection refused:** use the Runflare internal database hostname,
  correct credentials, and port `5432`; do not use `localhost` or `db`.
- **API is running but unreachable:** confirm the public network forwards to
  container port `8000` and uses `NodePort` for internet access.
- **Uploads disappear after deploy/restart:** attach the persistent disk at the
  exact path `/data/storage` and keep `STORAGE_ROOT=/data/storage`.
- **Upload returns `413`:** compare the service/proxy upload limit with
  `MAX_PDF_BYTES` (200 MiB by default) and ensure the service has enough memory
  and persistent disk space.
- **Browser reports CORS errors:** make `ADMIN_ORIGINS` exactly match the admin
  page's origin. Multiple origins are comma-separated.
- **Login succeeds but later requests return `401`:** confirm both sites use
  HTTPS, `COOKIE_SECURE=true`, and the frontend sends credentialed requests.
- **Old books cannot be opened after a secret change:** restore the original
  `BOOK_KEK_BASE64`. The wrapped book keys cannot be recovered without it.
- **Docker build cannot download an image or package:** check Runflare build
  events and support guidance. Runflare publishes mirrors for Docker registries
  and common package ecosystems, but do not rewrite the working `Dockerfile`
  unless logs show that a mirror is required.

## Go-live checklist

- [ ] The API and PostgreSQL are separate deployments in the same project.
- [ ] The API is built from this repository's `Dockerfile`.
- [ ] `DATABASE_URL` uses the internal Runflare database address.
- [ ] `APP_ENV=production` and `COOKIE_SECURE=true`.
- [ ] `JWT_SECRET` and `BOOK_KEK_BASE64` are stored as secrets and backed up.
- [ ] A persistent disk is mounted at `/data/storage`.
- [ ] Public traffic forwards to container port `8000`; PostgreSQL is private.
- [ ] The final admin origin is present in `ADMIN_ORIGINS`.
- [ ] The custom API domain has a valid HTTPS certificate.
- [ ] `/health` and `/api/v1/auth/status` both return `200`.
- [ ] Admin login, upload, publish, catalog, and restart-persistence tests pass.
- [ ] Matching database, disk, and encryption-secret backups exist off-platform.

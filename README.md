# Protected Book Backend

An independent, self-hostable backend for the protected PDF reader and its
Flutter Web admin app. It uses FastAPI, PostgreSQL, local private object storage,
and open-source cryptography. Supabase is not required.

## Cost model

The software stack is free and has no per-user or per-book license fee. Running
it on a developer machine or an existing server costs $0. A reliable public
production service still needs a machine, bandwidth, backups, and usually a
domain; no provider can guarantee those resources free forever.

## Run locally

```sh
cp .env.example .env
openssl rand -hex 32       # put the result in JWT_SECRET
openssl rand -base64 32    # put the result in BOOK_KEK_BASE64
docker compose up --build
```

API docs: `http://localhost:8000/docs`

Run the Flutter admin on port 8080 and select the remote adapters:

```sh
cd ../book-reader-ai
flutter run -d chrome --web-port 8080 --wasm \
  --dart-define=APP_ENV=development \
  --dart-define=API_BASE_URL=http://localhost:8000/api/v1/
```

If `API_BASE_URL` is omitted, the admin continues to use its browser-local demo
repositories.

## Verify

```sh
docker compose run --rm api pytest
docker compose run --rm api ruff check src tests
```

## Storage and publishing

The API accepts the admin PDF as a bounded staging upload, validates its PDF
signature, and writes only a versioned chunk-encrypted `.brc` object to durable
storage. Every 1 MiB chunk has its own AES-GCM nonce/tag and version/chunk AAD.
The per-version DEK is stored only after being wrapped by the environment KEK.

The original PDF is never served by the backend. This is practical protection,
not commercial DRM; a compromised/rooted client remains outside the guarantee.

See [admin-api.md](docs/api-contracts/admin-api.md) and
[threat-model.md](docs/security/threat-model.md).

For a step-by-step production setup, verification, backup, update, and
troubleshooting procedure, see [deployment.md](docs/deployment.md).

Beginner-friendly deployment guides for the backend, PostgreSQL, HTTPS, and
backups are available in [English](docs/deployment-en.md) and
[Persian](docs/deployment-fa.md).

For a Runflare-specific deployment using the existing Dockerfile, managed
PostgreSQL, and persistent book storage, see
[runflare-deployment.md](docs/runflare-deployment.md).

#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

. .venv/bin/activate

python -m pip install -q -e '.[dev]'

if [ ! -f .env ]; then
  cp .env.example .env
fi

# ensure a local PostgreSQL user/database exists for the default development config
if command -v psql >/dev/null 2>&1; then
  PGLOCAL="psql -h /tmp -U \"$(whoami)\" -d postgres -v ON_ERROR_STOP=1"
  if ! eval "$PGLOCAL -tAc \"SELECT 1 FROM pg_roles WHERE rolname='book_reader'\"" | grep -q 1; then
    eval "$PGLOCAL -c \"CREATE ROLE book_reader LOGIN PASSWORD 'book_reader';\""
  fi
  if ! eval "$PGLOCAL -tAc \"SELECT 1 FROM pg_database WHERE datname='book_reader'\"" | grep -q 1; then
    createdb -h /tmp -U "$(whoami)" book_reader
    eval "$PGLOCAL -c \"ALTER ROLE book_reader WITH LOGIN PASSWORD 'book_reader';\""
  fi
fi

export APP_ENV="${APP_ENV:-development}"
export DATABASE_URL="${DATABASE_URL:-postgresql+psycopg://book_reader:book_reader@localhost:5432/book_reader}"
export JWT_SECRET="${JWT_SECRET:-$(openssl rand -hex 32)}"
export BOOK_KEK_BASE64="${BOOK_KEK_BASE64:-$(openssl rand -base64 32)}"
export STORAGE_ROOT="${STORAGE_ROOT:-$PWD/data/storage}"
export ADMIN_ORIGINS="${ADMIN_ORIGINS:-http://localhost:8080,http://127.0.0.1:8080}"
export COOKIE_SECURE="${COOKIE_SECURE:-false}"
export MAX_PDF_BYTES="${MAX_PDF_BYTES:-209715200}"
export MAX_COVER_BYTES="${MAX_COVER_BYTES:-2097152}"

mkdir -p "$STORAGE_ROOT"

cat > .env <<EOF
APP_ENV=${APP_ENV}
DATABASE_URL=${DATABASE_URL}
JWT_SECRET=${JWT_SECRET}
BOOK_KEK_BASE64=${BOOK_KEK_BASE64}
STORAGE_ROOT=${STORAGE_ROOT}
ADMIN_ORIGINS=${ADMIN_ORIGINS}
COOKIE_SECURE=${COOKIE_SECURE}
MAX_PDF_BYTES=${MAX_PDF_BYTES}
MAX_COVER_BYTES=${MAX_COVER_BYTES}
EOF

python -m alembic upgrade head
exec python -m uvicorn src.main:app --host 127.0.0.1 --port 8000

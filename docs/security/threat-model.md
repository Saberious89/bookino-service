# MVP backend security boundary

The database and protected storage are private infrastructure. Flutter clients
receive REST DTOs, never database credentials. This is intentionally different
from Supabase's browser-accessible Data API model; authorization is performed in
the service and PostgreSQL is reachable only by the service network.

## Implemented

- Argon2 password hashing and short-lived, HttpOnly admin session cookies
- server-side role checks for every privileged operation
- immutable PDF versions
- chunked AES-256-GCM protected-book containers
- a random DEK for every version, wrapped by a server-only KEK
- no public protected-file route
- archive semantics instead of destructive book deletion
- device revocation and audit logging
- bounded PDF/cover upload sizes and file-signature checks

## Deployment requirements

- TLS is mandatory outside local development.
- Set unique production `JWT_SECRET` and `BOOK_KEK_BASE64` values in the secret
  environment; never place them in Flutter defines or source control.
- Keep PostgreSQL and `/data/storage/protected-books` off the public network.
- Back up the database, encrypted objects, and KEK separately. Losing the KEK
  makes every protected version permanently unreadable.
- Run the API with a non-root container/runtime user and restrict storage
  directory permissions in production.

## Deferred with the Reader app

Device public-key registration, signed seven-day offline licenses, reader
email/Google authentication, and reader progress/favorites/bookmarks APIs need
to be implemented and security-reviewed together with the Android client. The
database tables are present, but this backend does not claim those unfinished
flows are production-ready.


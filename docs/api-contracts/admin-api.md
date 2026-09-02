# Admin API contract

Base path: `/api/v1`. JSON uses the existing Flutter Admin field names so the
domain layer remains independent from the backend implementation.

## Authentication

- `GET auth/status` — first-admin and session state
- `POST auth/bootstrap-admin` — creates the only initial admin and sets an
  HttpOnly session cookie
- `POST auth/login` — verifies an admin and sets the cookie
- `POST auth/logout` — clears the cookie

Bootstrap is guarded by a PostgreSQL transaction-level advisory lock. Later
admin accounts must be created by a future authenticated role-management flow;
the public bootstrap endpoint never reopens.

## Administration

- `GET admin/snapshot`
- `POST admin/books` (`multipart/form-data`: nullable `id`, `title`, `author`,
  `description`, `categoryId`, `publicationYear`, `pageCount`, and `status`
  fields, plus optional `cover` and `pdf`). For compatibility with older admin
  builds, the former JSON `metadata` form field is still accepted but is no
  longer advertised by OpenAPI.
- `GET admin/books/{id}/protected-file` — downloads the current encrypted `.brc`
  container as an attachment. It requires an admin session, uses private
  no-store caching, and never decrypts the original PDF or returns key material.
- `POST admin/books/{id}/archive`
- `POST admin/categories`
- `PUT admin/categories/{id}`
- `POST admin/devices/{id}/revoke`
- `GET admin/analytics`

All routes in this section resolve the current user from the server-side
session and verify `role == admin`; client route visibility is never treated as
authorization.

## Public

- `GET catalog` — only published books with a ready current version
- `GET media/covers/...` — cover images only

No protected object path, wrapped DEK, plaintext checksum, or book license is
returned through the catalog.

# Changelog

## Unreleased

## 0.10.8 — 2026-08-01

### Fixes (S3 clients)
- ListObjects: default missing `list-type` to V2 (fixes S3 Browser `GET /{bucket}?delimiter=...` 400).
- Stub empty `ObjectLockConfiguration` for `?object-lock=` bucket probes.
- Pyrogram uploads: map `telegram_topic_id` to `reply_to_message_id` (fixes `message_thread_id` TypeError on PutObject).

## 0.10.7 — 2026-07-31

### Fixes
- `/api/health` always read `async_session_factory` via `app.db.session` at request time (fixes false 503 when DB was connected but health imported the initial `None` binding). Same pattern fixed for GC and management bot DB access.

## 0.10.6 — 2026-07-31

### Ops
- Log uvicorn-level readiness after startup: when Pyrogram is not ready, WARNING includes `last_error` hint (easier NAS debug for `/api/health` 503).

## 0.10.5 — 2026-07-31

### Fixes (deploy)
- Account-mode deploys no longer require `BOT_TOKEN`: legacy bot PTB `Application` is built lazily (fixes `InvalidToken` at import when token is unset or empty).
- Telegram package uses lazy imports so `account_client` does not pull in bot storage at startup.
- Pyrogram config errors set `last_error`; startup logs a concise warning when `/api/health` will stay 503 until `SESSION_STRING` is fixed.

## 0.10.4 — 2026-07-31

### Fixes (MySQL 8.0)
- `ix_blobs_bucket_path` uses `path(512)` prefix so utf8mb4 index stays within InnoDB 3072-byte limit (error 1071).

## 0.10.2 — 2026-07-31

### Fixes (MySQL 8.0 deploy)
- Schema: `users.description` as `VARCHAR(512)` (avoids `TEXT` + `DEFAULT` error 1101 on strict servers).
- Schema: blob object keys use `path_digest` + `UNIQUE (bucket_name, path_digest)` so `TEXT path` is not in a unique index (avoids error 1170).
- Docker: start with `uvicorn` instead of `fastapi run` (Click/Typer crash); image build exports deps from `poetry.lock`.

## 0.10.1 — 2026-07-30

### Security / ops (personal / home NAS)
- Startup rejects weak or missing `SECRET_KEY` (≥16 characters, no `.env.example` placeholders).
- `HEALTH_EXPOSE_ERRORS` defaults to `0` (no error strings on `/api/health`); set `HEALTH_EXPOSE_ERRORS=1` if monitoring or scripts relied on the previous default.
- SigV4 auth failures no longer log expected signature details.
- Deploy docs: home NAS + `TELEGRAM_PROXY` (LAN IP / `host.docker.internal`); Compose `extra_hosts` for app and setup.

## 0.10.0 — 2026-07-30

MySQL metadata store (breaking: no MongoDB migration; health `database` field). Docker/Linux deploy only.

### Storage
- Metadata store: **MySQL** (SQLAlchemy async + `aiomysql`); single database, multiple tables; startup `create_all` (no MongoDB).
- `/api/health` reports `database` instead of `mongodb`.
- Compose / `.env.example` use MySQL 8.4; optional external MySQL via `DATABASE_URL` (URL-encode passwords; built-in `db` uses `MYSQL_HOST=db` + `MYSQL_*`).
- Storage ABC module renamed to `app/storage/backend.py` so `from app.storage import storage` resolves to the runtime singleton (fixes GC and blob I/O).
- User password hashing uses `bcrypt` directly (avoids passlib/bcrypt version skew in tests).
- Share download: atomic `UPDATE … RETURNING` for download quota; claim before loading object bytes; release quota if blob read fails.
- List prefix / multipart list: explicit SQL `LIKE` escape for `%` and `_`.
- Schema: FK `credentials.owner_username` → `users`; `multipart_parts.upload_id` → `multipart_uploads` (CASCADE).
- Lockfile: run `make lock` (or `python -m uv tool run poetry lock` on Windows) after editing `pyproject.toml`; CI runs `scripts/verify_poetry_lock.py`.
- **Deploy:** official path is **Docker / Linux** (GHCR image + Compose). Standalone Windows `.exe` (PyInstaller) is **not** supported or shipped from this repo.
- Removed tracked `docs/superpowers/` from the repository (local-only).

## 0.9.0 — 2026-07-30

Feature-complete preview: S3-compatible gateway with Telegram (Pyrogram account) storage, REST control plane, and Docker Compose deploy.

### S3 API
- PutObject / GetObject / HeadObject / DeleteObject; ListBuckets; ListObjectsV2 (prefix, delimiter, CommonPrefixes)
- CopyObject (`x-amz-copy-source`); DeleteObjects (`POST ?delete` + Content-MD5)
- Multipart: Create / UploadPart / Complete / Abort / ListParts / ListMultipartUploads
- Presigned GET/PUT (`POST /api/v1/presign`); Range GET; conditional GET/HEAD headers
- HeadBucket / CreateBucket / DeleteBucket (empty only); GetBucketLocation / GetBucketVersioning stubs
- Public buckets (anonymous Get/Head); per-bucket Telegram chat/topic
- SSE-C (AES-GCM); unsupported sub-resources return **501** (no PutObject fall-through)
- SigV4 auth with `AccessDenied` / `InvalidAccessKeyId` / `SignatureDoesNotMatch`; pre-auth before buffering large bodies
- `x-amz-request-id` / `x-amz-id-2` middleware; `APP_LANG` for S3 error messages

### Trash & data lifecycle
- Soft delete: DeleteObject / DeleteObjects default to trash; restore via `/api/v1/trash`
- `x-telezon-bypass-trash: true` and `ENABLE_TRASH=0` for hard delete; trash inserted before live row removal
- Overwrites (PutObject, CopyObject, CompleteMultipart, Bearer upload) retire previous version via trash
- CopyObject: scoped read on same-account sources; cross-account only when source bucket is public

### REST & credentials
- Users, buckets, multi-credential RBAC (`readonly` / `readwrite`, optional bucket scope) via `/api/v1/credentials`
- Share links (password + lockout); Bearer simple upload `PUT /api/v1/upload/`
- Signup rolls back user if default bucket creation fails; owners manage own buckets
- Removed unused `API_KEY` and admin-only `/api/v1/blobs` listing
- Docs: `docs/AUTH-AND-SHARING.md`, `docs/S3-COMPAT.md`

### Telegram storage & reliability
- Account-mode Pyrogram backend only; single worker / shared `SESSION_STRING`
- Rate limiting, `MAX_UPLOAD_BYTES`, long-lived client; optional `TELEGRAM_PROXY`, Local Bot API base URL, disk cache
- Optional management bot (`ENABLE_MGMT_BOT`)

### Background operations
- GC: stale multipart uploads, expired shares, trash retention, pending TG deletes, orphan metadata sampler (confirmed-gone only)

### Deploy & release
- Clone-free production: Release assets (`docker-compose.yml`, `.env.example`, setup scripts, `docs/DEPLOY.zh-CN.md`, `README.zh-CN.md`)
- Interactive first login: `docker compose --profile setup run --rm setup`; `GET /api/health`; `HEALTH_EXPOSE_ERRORS`
- Session placeholder detection in `.env.example`; GitHub Release + GHCR on `v*` tags
- CI (pytest on push/PR); Docker publish on `v*` tags
- Multi-platform GHCR images: `linux/amd64`, `linux/arm64` (see `docs/RELEASE.md`)

## 0.1.0 — 2024-11
- Initial FastAPI + Mongo + Telegram S3 gateway (PUT/GET/HEAD)

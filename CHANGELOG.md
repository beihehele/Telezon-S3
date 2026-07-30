# Changelog

## Unreleased
- DeleteObjects (`POST ?delete` + Content-MD5)
- GetObject/HeadObject Range + conditional headers (If-Match / If-None-Match / …)
- Unsupported S3 sub-resources return 501 (no PutObject fall-through)
- Background GC for stale multipart uploads and expired shares (`ENABLE_GC`)
- CopyObject (`x-amz-copy-source`)
- ListMultipartUploads (`GET ?uploads`), GetBucketLocation stub
- HeadBucket / CreateBucket / DeleteBucket (empty only)
- Share password lockout (`SHARE_MAX_FAILED_ATTEMPTS`, `SHARE_LOCKOUT_SECONDS`)
- Bearer simple upload: `PUT /api/v1/upload/?bucket=&key=`
- Mount `/api` and `/share` before S3 catch-alls
- Fix blob overwrite `updated_at` (was UpdateResult)
- Cap CopyObject / share links at `MAX_UPLOAD_BYTES` (in-memory paths)
- Faster bucket size aggregate (no full blob materialization)
- REST bucket create/update aligned with S3: owners manage own buckets
- Remove unused `API_KEY` and admin-only `/api/v1/blobs`
- Document auth/upload/sharing choices in `docs/AUTH-AND-SHARING.md`
- Multi-credential RBAC (`readonly`/`readwrite`, optional bucket scope) via `/api/v1/credentials`
- ListObjectsV2 `delimiter` / CommonPrefixes; GetBucketVersioning stub
- `x-amz-request-id` / `x-amz-id-2` middleware
- GC: retry pending TG deletes + sample dead blob metadata (`GC_ORPHAN_SAMPLE_SIZE`)
- Soft delete / trash: DeleteObject defaults to trash; restore via `/api/v1/trash`;
  `x-telezon-bypass-trash: true` for hard delete; GC purges expired trash
- Overwrite paths (PutObject / CompleteMultipart / Bearer upload) use the same trash lifecycle
- S3 auth errors: `AccessDenied` / `InvalidAccessKeyId` vs `SignatureDoesNotMatch` when identity is known
- Signup rolls back the user if default bucket creation fails
- GC orphan sampler only deletes metadata on confirmed TG-gone errors
  (skips throttle / unavailable / unknown)
- Pre-auth identity+RBAC before buffering Put / UploadPart / DeleteObjects /
  Complete bodies
- Soft-delete inserts trash before removing the live blob row
- CopyObject enforces scoped read on same-account source buckets; docs clarify public-bucket semantics
- Release `docker-compose.yml`, setup scripts, and `docs/DEPLOY.zh-CN.md` for clone-free Compose deploy
- Interactive Telegram login: `docker compose --profile setup run --rm setup`
- `GET /api/health` (Mongo + Telegram readiness); set `HEALTH_EXPOSE_ERRORS=0` to hide error text on public URLs
- Ignore placeholder `SESSION_STRING` values from `.env.example`; clearer errors when Telegram env is missing

## 1.0.0 — 2026-07-29
- S3 protocol completeness: Delete, ListObjectsV2, ListBuckets, HEAD fix, Presign GET/PUT
- Reliable transport: long-lived TG client, rate limit, upload size cap, workers=1
- Isolation: public buckets, share links, per-bucket Telegram chat/topic
- Large files: multipart upload lifecycle, optional disk cache, Local Bot API base URL
- Security/ops: SSE-C (AES-GCM), i18n S3 errors, CI workflow, optional mgmt bot hooks
- Telegram SOCKS5/HTTP proxy via `TELEGRAM_PROXY`
- GitHub Release + GHCR publish workflows (`v*` tags)

## 0.1.0 — 2024-11
- Initial FastAPI + Mongo + Telegram S3 gateway (PUT/GET/HEAD)

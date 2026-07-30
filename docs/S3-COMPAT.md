# S3 Compatibility Matrix (Telezon-S3 1.1+)

Path-style endpoint: `http://host:port/{bucket}/{key}`

| Operation | Status | Notes |
|-----------|--------|-------|
| PutObject | Yes | Requires `Content-Length`; size stored as actual body length; optional SSE-C |
| GetObject | Yes | Public buckets skip auth; multipart objects stream parts; optional disk cache |
| HeadObject | Yes | Auth unless `is_public` |
| CopyObject | Yes | `x-amz-copy-source`; download-then-upload; source read RBAC + dest write; public source OK cross-account |
| DeleteObject | Yes | Default: soft-delete to trash (TG kept); `x-telezon-bypass-trash` / `ENABLE_TRASH=0` hard-deletes TG; clears disk cache |
| DeleteObjects | Yes | Same trash/hard semantics as DeleteObject; requires `Content-MD5`; Quiet mode supported |
| ListObjectsV2 | Yes | `list-type=2`, prefix, continuation, **delimiter / CommonPrefixes** |
| ListBuckets | Yes | `GET /`; scoped credentials only see allowed buckets |
| HeadBucket | Yes | `HEAD /{bucket}`; `x-amz-bucket-region: us-east-1` |
| CreateBucket | Yes | Primary key or unrestricted readwrite credential |
| DeleteBucket | Yes | `DELETE /{bucket}` only when empty |
| GetBucketLocation | Stub | `GET /{bucket}?location` → `us-east-1` |
| GetBucketVersioning | Stub | Always empty/disabled config |
| Presigned GET/PUT | Yes | Max 7 days; `POST /api/v1/presign`; prefers `PUBLIC_BASE_URL` |
| Multi-credential RBAC | Yes | `POST /api/v1/credentials` — `readonly` / `readwrite`, optional bucket list |
| CreateMultipartUpload | Yes | `POST ...?uploads` |
| UploadPart | Yes | Requires `Content-Length`; capped by `MAX_UPLOAD_BYTES` |
| CompleteMultipartUpload | Yes | Non-last parts ≥ `MULTIPART_MIN_PART_BYTES`; overwrite of live key uses trash lifecycle |
| AbortMultipartUpload | Yes | Best-effort unused-part TG cleanup (not trash — parts never became live objects) |
| ListParts | Yes | `GET ...?uploadId=` |
| ListMultipartUploads | Yes | `GET /{bucket}?uploads` |
| Share links | Yes | Humans; password + lockout; **in-memory**, capped at `MAX_UPLOAD_BYTES` |
| Soft delete / trash | Yes | Delete/overwrite (Put, Copy, Complete MPU, Bearer upload) -> trash; REST restore; bypass for hard delete |
| Bearer simple upload | Yes | Scripts/Shortcuts only — see [`AUTH-AND-SHARING.md`](AUTH-AND-SHARING.md) |
| Public buckets | Yes | `is_public`: anonymous Get/Head only; List still requires SigV4 |
| Per-bucket TG destination | Yes | `telegram_chat_id` / `telegram_topic_id` |
| Conditional GET/HEAD | Yes | `If-Match` / `If-None-Match` / `If-Modified-Since` / `If-Unmodified-Since` |
| Range GET | Yes | `Range: bytes=` → 206 Partial Content |
| SSE-C | Niche | AES-GCM; not shareable/copyable — freeze unless you need client-held keys |

## Ops notes
- Docker/account mode: `--workers 1` (shared SESSION_STRING)
- `MAX_UPLOAD_BYTES` (default 50MiB) per PutObject/part
- `MULTIPART_MIN_PART_BYTES` (default 5MiB) enforced on Complete for non-last parts
- `TELEGRAM_API_BASE` optional Local Bot API
- `CACHE_DIR` optional GET cache
- `APP_LANG`=`en`|`zh` for S3 error messages
- `TELEGRAM_ADMIN_IDS` required allowlist when `ENABLE_MGMT_BOT=1`
- `PUBLIC_BASE_URL` preferred host for presigned URLs
- `TELEGRAM_PROXY` optional SOCKS5/HTTP proxy URL for Bot API + account (Pyrogram) traffic
- `ENABLE_GC` (default on): abort stale multipart uploads and delete expired shares on an interval
- `SHARE_MAX_FAILED_ATTEMPTS` / `SHARE_LOCKOUT_SECONDS` for share password lockout
- `/api` and `/share` are registered before S3 catch-alls so they are not treated as buckets
- Credential / upload / sharing decision guide: [`AUTH-AND-SHARING.md`](AUTH-AND-SHARING.md)
- Responses include `x-amz-request-id` / `x-amz-id-2`
- GC also retries pending TG deletes and samples dead blob metadata (`GC_ORPHAN_SAMPLE_SIZE`)

Unsupported sub-resources (`acl`, `policy`, `tagging`, `lifecycle`, …) return **501 NotImplemented** and do not fall through to Put/Get/Delete.

Not implemented: ListObjects V1, versioning (real), ACL, tagging, lifecycle, UploadPartCopy, SSE-S3/KMS.

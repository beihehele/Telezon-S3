# Auth, upload, and sharing — which path to use

Telezon-S3 exposes several overlapping entry points on purpose (S3 clients, scripts, humans). Use this table; do not invent a fourth way.

## Credentials

| Credential | Where | Use for |
|------------|--------|---------|
| Access Key ID + Secret Key (SigV4) | User primary key | Full owner access to all owned buckets; CreateBucket |
| Scoped credentials | `POST /api/v1/credentials` | Extra keys: `readonly` or `readwrite`; optional `buckets` allow-list (empty = all owned buckets) |
| JWT Bearer (`/api/auth/login`) | `Authorization: Bearer <jwt>` | Management REST: users, buckets metadata, shares, credentials, presign helper |
| `Authorization: Bearer access_key:secret_key` | `PUT /api/v1/upload/` only | Simple script/Shortcuts upload **without** SigV4 |

S3 operations authenticate via SigV4. **Readonly** credentials may List/Get/Head; writes require **readwrite** or the primary owner key. Bucket-scoped keys apply to **every** bucket touched by the request (including CopyObject source and destination).

## Uploading

| Method | When |
|--------|------|
| **PutObject** (SigV4) | Default. Prefer this. |
| **Presigned PUT** (`POST /api/v1/presign`) | Browser/third-party upload without embedding secrets |
| **Multipart upload** | Object larger than `MAX_UPLOAD_BYTES` (or approaching TG limits) |
| **Bearer `/api/v1/upload/`** | Tiny automation/Shortcuts only; same size cap as PutObject |

## Sharing / reading without full secrets

| Method | Audience | Notes |
|--------|----------|-------|
| **Presigned GET** | Programs / temporary links | Prefer for automation; expiry enforced |
| **Share link** (`/share/{token}`) | Humans | Optional password + download cap + lockout; loads object into memory → capped at `MAX_UPLOAD_BYTES` |
| **Public bucket** (`is_public=true`) | Anonymous **Get/Head** on objects | Set via `PUT /api/v1/buckets/{name}` as owner; List and other bucket APIs still require SigV4. Does not make the bucket writable anonymously. |

Rule of thumb: **programs → Presign**; **one file to a person → Share**; **anonymous object GET/HEAD → Public** (not anonymous listing).

## Buckets

| Action | Preferred API |
|--------|----------------|
| Create / delete empty bucket | S3 `CreateBucket` / `DeleteBucket` (also available under `/api/v1/buckets` for owners) |
| Toggle `is_public`, set `telegram_chat_id` / `telegram_topic_id` | REST `PUT /api/v1/buckets/{name}` as **owner** (or admin) |
| Ownership transfer | REST update, **admin only** |

Signup creates a default bucket named after the username. Extra buckets are allowed.

## Soft delete / trash

| Action | How |
|--------|-----|
| Delete (default) | S3 DeleteObject / DeleteObjects → trash; **TG messages kept** |
| Overwrite (default) | PutObject / CopyObject / CompleteMultipartUpload / Bearer `PUT /api/v1/upload/` replacing a live key → previous version to trash |
| Hard delete | Header `x-telezon-bypass-trash: true`, or `ENABLE_TRASH=0` (immediate TG delete) |
| Abort MPU parts | Unused multipart parts are hard-deleted (never live objects) |
| List / restore / purge | `GET/POST/DELETE /api/v1/trash` (JWT, bucket owner) |
| Auto purge | GC after `TRASH_RETENTION_SECONDS` (default 7 days) |

### Auth error codes (S3)

| Situation | Code |
|-----------|------|
| Bad / missing signature for a known key | `SignatureDoesNotMatch` |
| Known key, valid signature, but role/bucket scope forbids the op | `AccessDenied` |
| Unknown access key id | `InvalidAccessKeyId` |

Restore fails with 409 if a live object already occupies the same key.

## CopyObject caveat

CopyObject is **download-then-reupload** through Telegram (not server-side). It is limited to `MAX_UPLOAD_BYTES` and does not copy SSE-C objects. Large objects: Get + Put or multipart.

The caller must be authorized to **write** the destination bucket (SigV4 on the Put) and to **read** the source bucket when it is owned by the same account (scoped credentials must include the source bucket name). Cross-account copy is allowed only when the source bucket is `is_public`.

## Intentionally niche / frozen

| Feature | Status |
|---------|--------|
| SSE-C | Supported but niche; not shareable/copyable |
| Management Telegram bot | Off by default (`ENABLE_MGMT_BOT=0`); thin stats only |
| Bot API storage backend | **Not used at runtime**; account (Pyrogram) mode only |
| GetBucketLocation | Stub always `us-east-1` |
| UploadPartCopy / ListObjects V1 / ACL / versioning | Not implemented |

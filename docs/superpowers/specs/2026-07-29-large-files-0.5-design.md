# Telezon-S3 0.5 — Large Files Design

**Date:** 2026-07-29  
**Auto-approved**

## Scope
1. S3 Multipart: CreateMultipartUpload, UploadPart, CompleteMultipartUpload, AbortMultipartUpload, ListParts
2. Optional `TELEGRAM_API_BASE` for Local Bot API (bot storage only)
3. Simple disk GET cache under `CACHE_DIR` with max bytes `CACHE_MAX_BYTES`

## Multipart model
- `multipart_uploads`: upload_id, bucket, key, owner_access_key, initiated_at, content_type
- `multipart_parts`: upload_id, part_number, etag, size, file_id, message_id
- Complete: create blob with `file` = special marker `multipart:{upload_id}` and `parts` list; GET streams parts in order
- Abort: delete part TG messages best-effort + remove metadata

## Non-goals
Full CDN/R2; VPS processor; image derivatives

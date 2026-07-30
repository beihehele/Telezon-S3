# Soft delete / trash — design (2026-07-30)

## Goal
Protect against accidental DeleteObject / DeleteObjects / overwrite without implementing S3 versioning.

## Approach (chosen)
- Separate Mongo collection `trash` (not a flag on `blobs`).
- Default delete moves metadata to trash; **Telegram messages stay** until purge.
- Restore via REST; S3 List/Get never see trash.
- Hard delete via header `x-telezon-bypass-trash: true` (or `ENABLE_TRASH=0`).
- GC purges expired trash rows and then deletes TG messages.

## Config
- `ENABLE_TRASH=1` (default on)
- `TRASH_RETENTION_SECONDS=604800` (7 days)

## REST
- `GET /api/v1/trash?bucket=&limit=`
- `POST /api/v1/trash/restore` `{ "trash_id": "..." }`
- `DELETE /api/v1/trash/{trash_id}` permanent
- `POST /api/v1/trash/empty` `{ "bucket": "..." }` optional

## Conflicts
- Restore fails with 409 if live key already exists.
- DeleteBucket: purge that bucket's trash (or reject if trash non-empty — purge preferred).

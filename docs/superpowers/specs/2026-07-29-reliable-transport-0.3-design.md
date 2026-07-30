# Telezon-S3 0.3 — Reliable Transport Design

**Date:** 2026-07-29  
**Status:** Auto-approved (user: review-pass → next phase without re-asking)  
**Depends on:** 0.2 S3 protocol completeness

## Goal

Reduce Telegram client churn and memory/FloodWait risk for object PUT/GET/DELETE without changing the S3 API surface.

## Scope

1. **Long-lived Telegram Account client** — start once in FastAPI lifespan; reuse for put/get/delete_message; stop on shutdown.
2. **Upload size limit** — `MAX_UPLOAD_BYTES` (default `52428800` = 50MiB); oversize → S3 XML `EntityTooLarge` 400.
3. **In-process TG rate limiter** — token bucket (~20/s global, burst 20) wrapping storage TG calls; wait with timeout → 503 `SlowDown`.
4. **Large-body spill** — if body > `UPLOAD_SPILL_THRESHOLD` (default 8MiB), write request body to temp file then upload from file path (still buffered for Telegram send, but avoids holding request + BytesIO duplicates longer than needed for small files). Keep simple: for 0.3, enforce size limit + reuse client; spill is optional if timeboxed.

## Non-goals

- Local Bot API / 2GB path
- Multipart
- Cross-process distributed rate limit
- Full orphan GC cron (defer; overwrite already best-effort deletes old message_id)

## Success criteria

- Consecutive PUT/GET do not construct a new Pyrogram Client per call when account storage is active
- Oversize PUT returns EntityTooLarge XML
- Unit tests for limiter + size gate; storage client singleton smoke test with Fake/mock
- Version bump to 0.3.0; update S3-COMPAT notes if new error codes

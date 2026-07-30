# Telezon-S3 0.6 — Security & Ops Design

**Date:** 2026-07-29  
**Auto-approved**

## Scope
1. SSE-C style: optional `x-amz-server-side-encryption-customer-key` (base64 32-byte) for PUT encrypt / GET decrypt (AES-256-GCM); store nonce+tag with blob
2. Minimal management bot: `/start` `/stats` `/buckets` when BOT_TOKEN set (optional background poller or webhook stub — prefer on-demand via existing setup scripts + thin command module invoked from lifespan if `ENABLE_MGMT_BOT=1`)
3. i18n: English/Chinese error message map for S3 XML Message field via `APP_LANG`
4. GitHub Actions: pytest on push/PR

## Non-goals
Full Mini App; complete i18n of admin REST

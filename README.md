# Telezon S3

**English** · [简体中文](README.zh-CN.md) · [Español](README.es.md)

Telezon S3 is an **Amazon S3–compatible** object storage service that uses **Telegram** (Pyrogram account mode) as the storage backend. Use standard tools such as AWS CLI, rclone, or boto3 with a custom `endpoint_url`.

- S3: Put/Get/Head/Delete, ListBuckets, ListObjectsV2, CopyObject, DeleteObjects, multipart upload, presigned URLs, Range/conditional GET, SSE-C, public buckets
- REST: users, buckets, credentials (RBAC), shares, trash, Bearer upload
- Ops: rate limits, optional disk cache, background GC, soft delete / trash

Further detail: [`docs/S3-COMPAT.md`](docs/S3-COMPAT.md), [`docs/AUTH-AND-SHARING.md`](docs/AUTH-AND-SHARING.md). Step-by-step deploy (Chinese): [`docs/DEPLOY.zh-CN.md`](docs/DEPLOY.zh-CN.md). Local dev and pytest: [`docs/DEVELOP.zh-CN.md`](docs/DEVELOP.zh-CN.md).

[![Release](https://img.shields.io/github/v/release/beihehele/Telezon-S3)](https://github.com/beihehele/Telezon-S3/releases)

> Run **one worker** per Telegram account (`SESSION_STRING` cannot be shared across processes).

## Deployment

Download `docker-compose.yml`, `.env.example`, and `setup-telegram.sh` / `setup-telegram.ps1` from [Releases](https://github.com/beihehele/Telezon-S3/releases) into an empty directory.

```bash
mkdir telezon-s3 && cd telezon-s3
VERSION=x.y.z
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/.env.example"
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/docker-compose.yml"
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/setup-telegram.sh"
cp .env.example .env
```

1. Edit `.env`: set `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`, `SECRET_KEY`, MySQL settings (`MYSQL_*` or `DATABASE_URL`), `INITIAL_ADMIN_*`. Leave **`SESSION_STRING` empty**.
2. First-time Telegram login (phone / code / 2FA, interactive TTY):

```bash
export IMAGE_TAG=${VERSION:-latest}
docker compose pull
docker compose --profile setup run --rm setup
```

Copy `SESSION_STRING=...` into `.env`. Optionally listen for `CID` during setup.

3. Start:

```bash
docker compose up -d
```

- Service: `http://localhost:8000` (host port = `.env` `PORT`; container listens on **8000**)
- Readiness: `http://localhost:8000/api/health` — JSON uses **`database`** and **`telegram`** (not `mongodb`; since 0.9+)
- Swagger: `http://localhost:8000/docs`
- Create S3 keys: log in with `INITIAL_ADMIN_*`, then `POST /api/v1/credentials`

<details>
<summary>App only (you already have MySQL)</summary>

Set `DATABASE_URL` in `.env`, then:

```bash
docker pull ghcr.io/beihehele/telezon-s3:${IMAGE_TAG:-latest}
docker run --rm -p 8000:8000 --env-file .env ghcr.io/beihehele/telezon-s3:${IMAGE_TAG:-latest}
```

</details>

**Requires:** Docker Compose, a [Telegram API application](https://my.telegram.org/apps), and a channel or group for storage (`CID`). On Windows, run the **Linux container** via Docker Desktop (no standalone `.exe` build from this project).

## Configuration

Use `.env` from `.env.example`. Common variables:

```env
PROJECT_NAME='Telezon S3'
PORT=8000
# ≥16 chars; copy from .env.example then replace (placeholders are rejected at startup)
SECRET_KEY=replace-with-openssl-rand-hex-32

MYSQL_USER=telezon
MYSQL_PASSWORD=change-me
MYSQL_DATABASE=TelezonS3
# Or: DATABASE_URL=mysql://user:pass@host:3306/TelezonS3  (URL-encode special chars in password)

TELEGRAM_API_ID=
TELEGRAM_API_HASH=
SESSION_STRING=
CID=

INITIAL_ADMIN_USER=admin
INITIAL_ADMIN_PASSWORD=change-me

# Docker/NAS: use LAN IP or host.docker.internal, not 127.0.0.1 inside the container
# TELEGRAM_PROXY=socks5://192.168.1.10:7890
# Optional: ENABLE_MGMT_BOT=1 and BOT_TOKEN=...
# Set HEALTH_EXPOSE_ERRORS=1 only when debugging /api/health
```

Full list and defaults: `.env.example` in your deploy directory. The first admin user is created on startup; **default bucket name equals username**. Create S3 access keys via the REST API after login.

Account mode uses **Pyrogram only** (not the legacy bot-file storage path).

## Usage

### boto3

```python
import boto3

s3 = boto3.client(
    "s3",
    aws_access_key_id="your_access_key_id",
    aws_secret_access_key="your_secret_key",
    endpoint_url="http://localhost:8000",
)

s3.upload_file("local_file.txt", "bucket_name", "object_key.txt")
s3.download_file("bucket_name", "object_key.txt", "downloaded.txt")
```

### Helper scripts (from a source checkout)

```bash
poetry run python upload_file.py \
  --access-key-id ... --secret-key ... \
  --bucket-name mybucket --input-path local.txt --output-path remote.txt

poetry run python download_file.py \
  --access-key-id ... --secret-key ... \
  --bucket-name mybucket --input-path remote.txt --output-path local.txt
```

### AWS CLI (example)

```bash
aws --endpoint-url http://localhost:8000 s3 ls
aws --endpoint-url http://localhost:8000 s3 cp ./file.txt s3://mybucket/key
```

## Limitations

Telegram rate and file-size limits apply. Suitable for personal or small-team use; for high-traffic public delivery, use dedicated object storage (S3, MinIO, etc.).

## License

MIT

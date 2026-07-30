# Telezon S3

Telezon S3 is a storage service compatible with Amazon S3 API that uses Telegram as a storage backend. It allows storing and retrieving files using standard S3 clients.

**Current tree:** S3 + multipart + shares (see [`CHANGELOG.md`](CHANGELOG.md) Unreleased). Last tagged release: **1.0.0**. Compatibility matrix: [`docs/S3-COMPAT.md`](docs/S3-COMPAT.md). Auth/upload/sharing guide: [`docs/AUTH-AND-SHARING.md`](docs/AUTH-AND-SHARING.md).

[![CI](https://github.com/beihehele/Telezon-S3/actions/workflows/ci.yml/badge.svg)](https://github.com/beihehele/Telezon-S3/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/beihehele/Telezon-S3)](https://github.com/beihehele/Telezon-S3/releases)
[![GHCR](https://img.shields.io/badge/ghcr.io-beihehele%2Ftelezon--s3-blue)](https://github.com/beihehele/Telezon-S3/pkgs/container/telezon-s3)

> Account-mode deployments must run a **single worker** (`Dockerfile` default). Do not scale to multiple processes with the same `SESSION_STRING`.

## Quick start (published image)

```bash
docker pull ghcr.io/beihehele/telezon-s3:latest
cp .env.example .env
# edit .env
IMAGE_TAG=latest docker compose up -d
```

Image tags published on each `v*` GitHub tag: `latest`, `x.y.z`, `x.y`, `sha-<commit>`.

## Docker Deployment

The easiest way to run Telezon S3 is using Docker Compose:

1. Clone the repository
2. Copy the environment variables file:

```bash
cp .env.example .env
```

3. Configure the variables in the `.env` file
4. Start the services:

```bash
docker-compose up -d
```

The service will be available at `http://localhost:8000`

## API Documentation

The interactive API documentation is available through Swagger UI. You can access it at:

```
http://localhost:8000/docs
```

S3 operation coverage for this release is listed in [`docs/S3-COMPAT.md`](docs/S3-COMPAT.md).

## Development Requirements

- Python 3.12+
- Poetry
- Docker and Docker Compose
- A Telegram account or bot
- A Telegram channel

## Configuration

1. Clone the repository
2. Copy the `.env.example` file to `.env` and configure the environment variables:

```bash
cp .env.example .env
```

### Important Environment Variables

```env
# Server Configuration
PROJECT_NAME='Telezon S3'
PORT=8000
SECRET_KEY=your_secret_key

# MongoDB Configuration
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_USER=admin
MONGO_PASSWORD=your_password
DATABASE_NAME=TelezonS3

# Telegram Configuration
BOT_TOKEN=your_bot_token
CID=your_channel_id
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
SESSION_STRING=your_session_string
# Optional outbound proxy (SOCKS5 recommended)
# TELEGRAM_PROXY=socks5://user:pass@127.0.0.1:1080
```

### Initial Admin User

The system allows configuring an initial admin user through environment variables:

```env
INITIAL_ADMIN_USER=admin
INITIAL_ADMIN_PASSWORD=admin
```

These credentials will be used to automatically create the first admin user in the system during database initialization.

## Development

1. Install dependencies:

```bash
poetry install
```

2. Start the server in development mode:

```bash
make dev
```

### Telegram storage setup

Account mode (Pyrogram) is the **only** runtime backend:

```bash
make setup_account_storage
```

> Bot API storage (`make setup_bot_storage`) is legacy and is **not** selected by the server. Do not use it for new deployments.

## Usage

### Python Client (boto3)

```python
import boto3

s3 = boto3.client(
    's3',
    aws_access_key_id='your_access_key_id',
    aws_secret_access_key='your_secret_key',
    endpoint_url='http://localhost:8000'  # Or your production URL
)

# Upload file
s3.upload_file('local_file.txt', 'bucket_name', 'destination_name.txt')

# Download file
s3.download_file('bucket_name', 'destination_name.txt', 'downloaded_file.txt')
```

### Quick Upload and Download Script

The project includes utility scripts for uploading and downloading files:

```bash
poetry run python upload_file.py \
 --access-key-id your_access_key_id \
 --secret-key your_secret_key \
 --bucket-name bucket_name \
 --input-path local_file.txt \
 --output-path destination_name.txt
```

```bash
poetry run python download_file.py \
 --access-key-id your_access_key_id \
 --secret-key your_secret_key \
 --bucket-name bucket_name \
 --input-path remote_file.txt \
 --output-path local_destination_file.txt
```

## Available Make Commands

- `make dev`: Start server in development mode
- `make run`: Start server in production mode
- `make format`: Format code using ruff
- `make setup_account_storage`: Set up Telegram account (Pyrogram) session
- `make export`: Export dependencies to requirements.txt

> `make setup_bot_storage` remains in the Makefile for legacy scripts only.

## GitHub Releases

Pushing a version tag triggers packaging (same pattern as SaveAny-Bot):

```bash
git tag v1.0.0
git push origin v1.0.0
```

This runs:

1. **Build Release** — creates a GitHub Release, attaches source archives + docs, fills notes via `changelogithub`
2. **Build and Publish Docker Image** — pushes to `ghcr.io/beihehele/telezon-s3`

First-time GHCR note: if the package is private, grant pull access or set the package visibility to Public under GitHub → Packages.

## Features

- Compatible with Amazon S3 API
- Uses Telegram as storage backend
- Support for basic S3 operations (upload/download)
- Integration with standard S3 clients

## Contributing

Contributions are welcome. Please open an issue to discuss proposed changes.

## Important note about scalability:

For high-traffic projects, Telegram's limitations might eventually become a bottleneck that can't be circumvented. In such cases, I'd recommend using actual S3 or another storage solution specifically designed for high-concurrency file serving.
This project works great for personal/small deployments, but it's important to acknowledge its limitations for production environments with high demand.

## License

MIT
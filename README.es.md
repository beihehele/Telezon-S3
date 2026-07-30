# Telezon S3

[English](README.md) · [简体中文](README.zh-CN.md) · **Español**

Telezon S3 es un servicio compatible con la **API de Amazon S3** que usa **Telegram** (cuenta Pyrogram) como almacenamiento. Funciona con AWS CLI, rclone o boto3 usando `endpoint_url` personalizado.

Documentación: [`docs/S3-COMPAT.md`](docs/S3-COMPAT.md), [`docs/AUTH-AND-SHARING.md`](docs/AUTH-AND-SHARING.md). Guía de despliegue (chino): [`docs/DEPLOY.zh-CN.md`](docs/DEPLOY.zh-CN.md).

[![Release](https://img.shields.io/github/v/release/beihehele/Telezon-S3)](https://github.com/beihehele/Telezon-S3/releases)

> Un **solo worker** por cuenta de Telegram (`SESSION_STRING` no se comparte entre procesos).

## Despliegue

Descarga `docker-compose.yml`, `.env.example` y scripts de setup desde [Releases](https://github.com/beihehele/Telezon-S3/releases).

```bash
mkdir telezon-s3 && cd telezon-s3
VERSION=x.y.z
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/.env.example"
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/docker-compose.yml"
cp .env.example .env
export IMAGE_TAG=${VERSION:-latest}
docker compose pull
docker compose --profile setup run --rm setup
# pega SESSION_STRING en .env
docker compose up -d
```

- Servicio: `http://localhost:8000`
- Salud: `http://localhost:8000/api/health`
- Swagger: `http://localhost:8000/docs`

## Configuración

Variables principales en `.env` (ver `.env.example`):

```env
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
SESSION_STRING=
CID=
SECRET_KEY=...
INITIAL_ADMIN_USER=admin
INITIAL_ADMIN_PASSWORD=...
```

## Uso

### boto3

```python
import boto3

s3 = boto3.client(
    "s3",
    aws_access_key_id="...",
    aws_secret_access_key="...",
    endpoint_url="http://localhost:8000",
)
s3.upload_file("local.txt", "bucket", "key.txt")
```

## Licencia

MIT

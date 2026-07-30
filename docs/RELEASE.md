# GitHub packaging & release

Aligned with SaveAny-Bot: tag-driven Release + GHCR image publish.

## Trigger

```bash
git tag v1.0.1
git push origin v1.0.1
```

Tags must match `v*` (e.g. `v1.0.0`, `v1.2.3-rc.1`). Prerelease tags containing `-` mark the GitHub Release as prerelease.

## Workflows

| Workflow | File | Output |
|----------|------|--------|
| Build Release | `.github/workflows/build-release.yml` | GitHub Release + source archives + `.env.example` + `docker-compose.yml` + setup scripts + `README.zh-CN.md` + `docs/DEPLOY.zh-CN.md`; notes via `changelogithub` |
| Build and Publish Docker Image | `.github/workflows/build-docker.yml` | `ghcr.io/beihehele/telezon-s3` tags: `latest`, `x.y.z`, `x.y`, `sha-<short>` |
| CI | `.github/workflows/ci.yml` | pytest on push/PR (does not publish) |

## Consume image

No git clone required for production:

```bash
mkdir telezon-s3 && cd telezon-s3
VERSION=x.y.z
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/.env.example"
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/docker-compose.yml"
cp .env.example .env
# edit TELEGRAM_API_ID / TELEGRAM_API_HASH; leave SESSION_STRING empty
export IMAGE_TAG=${VERSION:-latest}
docker compose pull
docker compose --profile setup run --rm setup
# paste SESSION_STRING into .env, then:
docker compose up -d
```

See [DEPLOY.zh-CN.md](DEPLOY.zh-CN.md) for the full Compose guide.

Or pull only:

```bash
docker pull ghcr.io/beihehele/telezon-s3:${VERSION:-latest}
```

## Permissions

- Release job: `contents: write` (default `GITHUB_TOKEN`)
- Docker job: `packages: write` for GHCR

No extra secrets are required for public repos owned by the same actor that pushes tags.

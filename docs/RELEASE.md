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
| Build Release | `.github/workflows/build-release.yml` | GitHub Release + source `.tar.gz`/`.zip` + LICENSE/README/CHANGELOG/`.env.example`; notes via `changelogithub` |
| Build and Publish Docker Image | `.github/workflows/build-docker.yml` | `ghcr.io/beihehele/telezon-s3` tags: `latest`, `x.y.z`, `x.y`, `sha-<short>` |
| CI | `.github/workflows/ci.yml` | pytest on push/PR (does not publish) |

## Consume image

```bash
docker pull ghcr.io/beihehele/telezon-s3:1.0.0
IMAGE_TAG=1.0.0 docker compose up -d
```

## Permissions

- Release job: `contents: write` (default `GITHUB_TOKEN`)
- Docker job: `packages: write` for GHCR

No extra secrets are required for public repos owned by the same actor that pushes tags.

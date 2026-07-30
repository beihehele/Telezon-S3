FROM python:3.12-alpine

ARG VERSION=dev
ARG GitCommit=Unknown
ARG BuildTime=Unknown

LABEL org.opencontainers.image.title="Telezon-S3" \
      org.opencontainers.image.description="S3-compatible storage gateway backed by Telegram" \
      org.opencontainers.image.source="https://github.com/beihehele/Telezon-S3" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${GitCommit}" \
      org.opencontainers.image.created="${BuildTime}"

ENV APP_VERSION=${VERSION} \
    APP_GIT_COMMIT=${GitCommit} \
    APP_BUILD_TIME=${BuildTime}

RUN apk add --no-cache \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    make

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir poetry poetry-plugin-export \
    && poetry export -f requirements.txt --output requirements.txt --without-hashes --without dev \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "cryptography>=44.0.0" "socksio>=1.0.0" "httpx[socks]>=0.27.0"

COPY . .

EXPOSE 8000

# Single worker required: Telegram account SESSION_STRING cannot be shared across processes.
CMD ["fastapi", "run", "--workers", "1", "app/main.py"]

# Telezon S3

[English](README.md) · **简体中文** · [Español](README.es.md)

Telezon S3 是一套兼容 **Amazon S3 API** 的对象存储服务，底层使用 **Telegram**（Pyrogram 账号模式）作为存储后端，可用 AWS CLI、rclone、boto3 等通过自定义 `endpoint_url` 访问。

- **S3：** Put/Get/Head/Delete、ListBuckets、ListObjectsV2、CopyObject、DeleteObjects、分片上传、预签名、Range/条件请求、SSE-C、公共桶等（详见 [`docs/S3-COMPAT.md`](docs/S3-COMPAT.md)）
- **REST：** 用户、桶、多凭证 RBAC、分享、回收站、Bearer 直传（详见 [`docs/AUTH-AND-SHARING.md`](docs/AUTH-AND-SHARING.md)）
- **运维：** 限流、可选磁盘缓存、后台 GC、软删除/回收站

[![Release](https://img.shields.io/github/v/release/beihehele/Telezon-S3)](https://github.com/beihehele/Telezon-S3/releases)

> 每个 Telegram 账号仅运行 **单 worker**，勿在多进程间共用同一条 `SESSION_STRING`。

## 部署

在空目录从 [Releases](https://github.com/beihehele/Telezon-S3/releases) 下载 `docker-compose.yml`、`.env.example`、`setup-telegram.sh` / `setup-telegram.ps1`。更细的步骤见 **[docs/DEPLOY.zh-CN.md](docs/DEPLOY.zh-CN.md)**。

```bash
mkdir telezon-s3 && cd telezon-s3
VERSION=x.y.z
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/.env.example"
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/docker-compose.yml"
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/setup-telegram.sh"
cp .env.example .env
```

**Windows（PowerShell）：** 将上述 `curl` 换成 `Invoke-WebRequest`，并下载 `setup-telegram.ps1`。

1. **配置 `.env`**：填写 [my.telegram.org](https://my.telegram.org/apps) 的 `TELEGRAM_API_ID`、`TELEGRAM_API_HASH`，以及 `SECRET_KEY`、MySQL（`MYSQL_*` 或 `DATABASE_URL`）、`INITIAL_ADMIN_*`；**`SESSION_STRING` 先留空**。
2. **首次 Telegram 登录**（需交互终端：手机号 / 验证码 / 两步验证）：

```bash
export IMAGE_TAG=${VERSION:-latest}
docker compose pull
docker compose --profile setup run --rm setup
```

将输出的 `SESSION_STRING=...` 写入 `.env`；可按提示获取 `CID`。

3. **启动：**

```bash
docker compose up -d
```

- 服务：`http://localhost:8000`（`.env` 中 `PORT` 为宿主机端口，容器内固定 **8000**）
- 就绪：`http://localhost:8000/api/health`（JSON 字段为 **`database`** / **`telegram`**，不再返回 `mongodb`）
- 文档：`http://localhost:8000/docs`
- 使用 `INITIAL_ADMIN_*` 登录 REST 后，在 `/api/v1/credentials` 创建 S3 访问密钥

<details>
<summary>仅运行应用（已有 MySQL）</summary>

在 `.env` 中配置 `DATABASE_URL` 后：

```bash
docker pull ghcr.io/beihehele/telezon-s3:${IMAGE_TAG:-latest}
docker run --rm -p 8000:8000 --env-file .env ghcr.io/beihehele/telezon-s3:${IMAGE_TAG:-latest}
```

</details>

**需要：** Docker Compose、[Telegram API 应用](https://my.telegram.org/apps)、用于存储的频道或群组（`CID`）。Windows 请用 Docker Desktop 跑 **Linux 容器**（本仓库不提供独立 `.exe` 发行）。

## 配置说明

部署目录使用 `.env`（由 `.env.example` 复制）。常用项：

```env
PROJECT_NAME='Telezon S3'
PORT=8000
SECRET_KEY=请改为强随机串

MYSQL_USER=telezon
MYSQL_PASSWORD=请修改
MYSQL_DATABASE=TelezonS3
# 或 DATABASE_URL=mysql://user:pass@host:3306/TelezonS3

TELEGRAM_API_ID=
TELEGRAM_API_HASH=
SESSION_STRING=
CID=

INITIAL_ADMIN_USER=admin
INITIAL_ADMIN_PASSWORD=请修改

# 可选：TELEGRAM_PROXY=socks5://127.0.0.1:1080
# 可选：ENABLE_MGMT_BOT=1 时需 BOT_TOKEN
# 公网建议：HEALTH_EXPOSE_ERRORS=0
```

完整变量见同目录 `.env.example`。首次启动会创建管理员；**默认桶名与用户名相同**。登录 REST 后创建 S3 凭证。运行时仅 **Pyrogram 账号模式**（不要用遗留的 bot 文件存储流程）。

## 使用

### boto3

```python
import boto3

s3 = boto3.client(
    "s3",
    aws_access_key_id="AccessKey",
    aws_secret_access_key="SecretKey",
    endpoint_url="http://localhost:8000",
)

s3.upload_file("本地.txt", "桶名", "对象键.txt")
s3.download_file("桶名", "对象键.txt", "下载.txt")
```

### AWS CLI 示例

```bash
aws --endpoint-url http://localhost:8000 s3 ls
aws --endpoint-url http://localhost:8000 s3 cp ./file.txt s3://桶名/对象键
```

### 辅助脚本（需克隆源码后）

```bash
poetry run python upload_file.py --access-key-id ... --secret-key ... \
  --bucket-name 桶名 --input-path local.txt --output-path remote.txt
poetry run python download_file.py --access-key-id ... --secret-key ... \
  --bucket-name 桶名 --input-path remote.txt --output-path local.txt
```

## 规模与限制

适合个人或小团队场景；受 Telegram 频率与单文件大小限制。高并发对外分发请使用专用对象存储（S3、MinIO 等）。

## 许可证

MIT

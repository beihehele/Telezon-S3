# Telezon S3 生产部署（Docker Compose）

无需克隆仓库。从 [Releases](https://github.com/beihehele/Telezon-S3/releases) 下载 `docker-compose.yml`、`.env.example` 与 `setup-telegram.sh` / `setup-telegram.ps1` 到同一目录。

## 1. 准备文件

```bash
mkdir telezon-s3 && cd telezon-s3
VERSION=x.y.z
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/.env.example"
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/docker-compose.yml"
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/setup-telegram.sh"
cp .env.example .env
```

## 2. 编辑 `.env`（先不要启动服务）

| 项 | 说明 |
|----|------|
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | [my.telegram.org](https://my.telegram.org/apps) 申请 |
| `SESSION_STRING` | **留空**，下一步交互生成 |
| `SECRET_KEY` / `MONGO_PASSWORD` / `INITIAL_ADMIN_PASSWORD` | 改为强密码 |
| `CID` | 默认存储频道/群 ID；setup 可监听消息获取。未配置时服务启动会记录警告 |
| `BOT_TOKEN` | 仅 `ENABLE_MGMT_BOT=1` 时需要 |
| `PORT` | 宿主机访问端口（Compose 映射为 `PORT:8000`，容器内固定 8000） |

## 3. 首次 Telegram 登录（必须交互）

Telegram 首次登录需要手机号、验证码、可能还有两步验证密码，**无法**在纯后台 `docker compose up` 里完成。

```bash
export IMAGE_TAG=${VERSION:-latest}
docker compose pull
docker compose --profile setup run --rm setup
```

或执行同目录下的 `setup-telegram.sh` / `setup-telegram.ps1`。

按提示操作后，将终端输出的 `SESSION_STRING=...` **整行写入 `.env`**。可选：在 setup 结束时选择监听频道消息以获取 `CID`。

> Windows：在 PowerShell 中执行 `docker compose --profile setup run --rm setup`（Compose 已为 `setup` 服务配置 TTY）。

## 4. 启动

```bash
docker compose up -d
```

- API 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:<PORT>/api/health`（Mongo + Telegram 均就绪时为 200）
- 公网部署时建议设 `HEALTH_EXPOSE_ERRORS=0`；Mongo 默认仅绑定 `127.0.0.1:27017`，不需要本机直连时可删掉 `db.ports`

## 5. 创建 S3 凭证

使用 `INITIAL_ADMIN_*` 登录 REST API，在 `/api/v1/credentials` 创建 Access Key，供 boto3 / AWS CLI 使用。

## 常见问题

- **`telegram.ok: false`**：检查 `.env` 中 `SESSION_STRING` 是否完整、无换行截断；会话失效则重新跑 setup。
- **换 Telegram 账号**：重新执行 setup，更新 `SESSION_STRING` 后 `docker compose up -d` 重启 app。
- **仅更新镜像**：`docker compose pull && docker compose up -d`。

本地开发请克隆仓库，使用根目录 `docker-compose.yaml`（从源码 build）。

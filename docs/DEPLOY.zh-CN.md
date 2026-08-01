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
| `SECRET_KEY` / `MYSQL_PASSWORD` / `INITIAL_ADMIN_PASSWORD` | 改为强密码；`SECRET_KEY` 至少 16 字符且勿用 `.env.example` 占位符（否则启动失败） |
| `MYSQL_USER` / `MYSQL_DATABASE` | 外置或内置 MySQL 均需；默认库名 `TelezonS3` |
| `MYSQL_ROOT_PASSWORD` | **仅** Compose 内置 `db` 服务需要；外置 MySQL 可省略 |
| `DATABASE_URL` | **可选**：使用已有 MySQL 时设为 `mysql://用户:密码@主机:3306/库名`（密码含 `@`、`#`、`:` 等须 [URL 编码](https://docs.python.org/3/library/urllib.parse.html#urllib.parse.quote_plus)；应用会转为 `mysql+aiomysql://`）。Compose 内置 `db` 时只需设 `MYSQL_*`，应用容器内 `MYSQL_HOST=db`，**不要**在 compose 里手写未编码的 `DATABASE_URL` |
| `CID` | 默认存储频道/群 ID；setup 可监听消息获取。未配置时服务启动会记录警告 |
| `BOT_TOKEN` | 仅 `ENABLE_MGMT_BOT=1` 或旧版 bot 存储脚本需要；**账户模式请留空**，勿写空字符串或占位符 |
| `PORT` | 宿主机访问端口（Compose 映射为 `PORT:8000`，容器内固定 8000） |

### 家庭 NAS + Telegram 代理

国内或无法直连 Telegram 时，在 `.env` 设置 `TELEGRAM_PROXY`（SOCKS5/HTTP，见 `app/core/telegram_proxy.py`）。

- **容器内不要用 `127.0.0.1`**：代理若在 NAS 宿主机上，应写 **局域网 IP**（如 `socks5://192.168.1.10:7890`），或 `socks5://host.docker.internal:7890`（Release 版 `docker-compose.yml` 已为 `app` / `setup` 配置 `extra_hosts: host.docker.internal:host-gateway`）。
- 首次登录 Telegram 时 `setup` 容器同样需要能走代理，请保证 `TELEGRAM_PROXY` 在 `setup` 的 `env_file` 中已配置。
- 单容器、单 worker、仅内网访问时，保持默认 `HEALTH_EXPOSE_ERRORS=0` 即可；需要排障时再临时设为 `1`。

### 使用已有 MySQL（不启动 Compose 里的 `db`）

适用于 **MySQL 8.0** 等已有实例（含 NAS 上独立安装的 MySQL）。

1. 在 MySQL 中预先创建空库（如 `TelezonS3`），并授予应用用户建表与读写权限，例如：
   ```sql
   CREATE DATABASE TelezonS3 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   GRANT ALL PRIVILEGES ON TelezonS3.* TO 'telezon'@'%';
   FLUSH PRIVILEGES;
   ```
2. 在 `.env` 中设置 `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE`，或一条 `DATABASE_URL`（密码含特殊字符须 URL 编码）。
3. **`MYSQL_HOST` 必须是 app 容器能访问的地址**：同一台 NAS 上 MySQL 若只监听 `127.0.0.1`，容器内应使用 `host.docker.internal`（需 compose 的 `extra_hosts`）或宿主机局域网 IP，**不要**在容器里写 `127.0.0.1` 指宿主机 MySQL。
4. 从 `docker-compose.yml` 中删除 `db` 服务及 `app.depends_on.db`；删除 `app.environment` 里的 `MYSQL_HOST: db`（若存在）。仅保留 `app`（与可选 `setup`）。
5. 首次启动时应用会自动建表（`CREATE TABLE`）。**无 Alembic**；若曾建表失败或从低于 0.10.2 的版本升级，见下文「升级与空库」。

### 超级群 Topic 与 S3 桶

- `.env` 的 **`CID`** 填开启 **话题（Forum）** 的超级群 chat id。
- S3 桶与 Topic 的绑定在 **REST**（`/docs` → `PUT /api/v1/buckets/{name}`）设置 `telegram_topic_id`；S3 `CreateBucket` 不会写入 Topic。
- 安装时自动创建的管理员同名桶也需设置 `telegram_topic_id`，否则文件会落在群的非 Topic 区域。

## 3. 首次 Telegram 登录（必须交互）

Telegram 首次登录需要手机号、验证码、可能还有两步验证密码，**无法**在纯后台 `docker compose up` 里完成。

```bash
export IMAGE_TAG=${VERSION:-0.10.10}
docker compose pull
docker compose --profile setup run --rm setup
```

或执行同目录下的 `setup-telegram.sh` / `setup-telegram.ps1`。

按提示操作后，将终端输出的 `SESSION_STRING=...` **整行写入 `.env`**。可选：在 setup 结束时选择监听频道消息以获取 `CID`。

> Windows：在 PowerShell 中执行 `docker compose --profile setup run --rm setup`（Compose 已为 `setup` 服务配置 TTY）。

## 4. 启动

```bash
export IMAGE_TAG=${IMAGE_TAG:-0.10.10}
docker compose up -d
```

若你自行改过启动命令：官方 **0.10.2+** 镜像已用 `uvicorn` 启动；**0.10.4+** 含 MySQL 索引 1071 修复；**0.10.5+** 账户模式无需 `BOT_TOKEN`。更早镜像若出现 `fastapi` / `Secondary flag` 崩溃，可在 compose 的 `app` 上覆盖：

```yaml
command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

- API 文档：`http://localhost:<PORT>/docs`（`PORT` 为 `.env` 宿主机端口）
- 健康检查：`http://localhost:<PORT>/api/health`（`database.ok` 与 `telegram.ok` 均为 true 时为 200；**0.9+** 使用 `database`，不再返回 `mongodb`）
- 默认不向健康检查响应暴露 `database.error` / `telegram.error`；排障时可设 `HEALTH_EXPOSE_ERRORS=1`。内置 MySQL 默认仅绑定 `127.0.0.1:3306`，不需要本机直连时可删掉 `db.ports`

## 5. 创建 S3 凭证

使用 `INITIAL_ADMIN_*` 登录 REST API，在 `/api/v1/credentials` 创建 Access Key，供 boto3 / AWS CLI 使用。

## 6. 升级与空库（MySQL 8.0，建议 ≥0.10.10）

| 版本 | 说明 |
|------|------|
| **0.10.9+** | S3 Browser：`GET /{bucket}/?delimiter=...` 列表不再 400 |
| **0.10.8+** | S3 Browser：列表默认 V2；Pyrogram 话题上传修复 |
| **0.10.7+** | 修复 `/api/health` 误报 503（数据库已连接但探活仍失败） |
| **0.10.6+** | 启动日志明确 Pyrogram 是否 ready（503 时看 WARNING 里的 Detail） |
| **0.10.5+** | 账户模式可不配置 `BOT_TOKEN`（避免启动时 InvalidToken） |
| **0.10.4+** | 修复 `ix_blobs_bucket_path` 在 utf8mb4 下错误 1071（`path(512)` 前缀） |
| **0.10.2+** | 修复 MySQL 建表（`users.description`、`blobs.path_digest`）；Docker 使用 `uvicorn` + 构建锁定 `poetry.lock` |
| **低于 0.10.2** | 外置 MySQL 上可能遇到建表错误（如 1101 / 1170）或容器 `fastapi run` 启动失败 |

**推荐升级步骤（个人 NAS、可接受清空元数据）：**

```bash
export IMAGE_TAG=0.10.10
docker compose pull
docker compose up -d --force-recreate
```

若日志里仍是 **建表失败**，在 MySQL 上清空应用库后重启（**会删除所有桶/对象元数据**，Telegram 上的文件消息不会自动删）：

```sql
DROP DATABASE TelezonS3;
CREATE DATABASE TelezonS3 CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

然后再次 `docker compose up -d`，日志中应出现 `Connected to MySQL`。

**已有数据、不能删库：** 当前版本**不提供**自动迁移脚本；需自行对照 `app/db/tables.py` 手工 `ALTER TABLE`（例如为 `blobs` 增加 `path_digest` 并回填），适合进阶用户。

## 常见问题

- **`database.ok: false`**：检查 `DATABASE_URL` / `MYSQL_*`、网络与账号权限；可设 `HEALTH_EXPOSE_ERRORS=1` 查看 `database.error`。在容器内测试：`python -c "import socket; socket.create_connection(('你的MYSQL_HOST',3306),5)"`。
- **建表报错 1101 / 1170 / 1071**：请使用 **0.10.4+** 镜像并对空库执行 `create_all`（见「升级与空库」）。1071 多为 `path(768)` 索引；0.10.4 改为 `path(512)`。
- **启动报 InvalidToken / 未配 BOT_TOKEN**：账户模式请用 **0.10.5+**，并删除 `.env` 中空 `BOT_TOKEN=`。
- **`Can't connect to MySQL server` / 超时**：检查 `MYSQL_HOST` 对容器是否可达（勿用指向容器自身的 `127.0.0.1`）。
- **`telegram.ok: false`**：检查 `.env` 中 `SESSION_STRING` 是否完整、无换行截断；会话失效则重新跑 setup。
- **换 Telegram 账号**：重新执行 setup，更新 `SESSION_STRING` 后 `docker compose up -d` 重启 app。
- **仅更新镜像**：`docker compose pull && docker compose up -d`。

本地开发请克隆仓库，使用根目录 `docker-compose.yaml`（从源码 build）。

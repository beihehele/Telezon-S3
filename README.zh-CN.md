# Telezon S3

[English](README.md) · **简体中文** · [Español](README.es.md)

Telezon S3 是一套兼容 **Amazon S3 API** 的对象存储服务，底层使用 **Telegram**（Pyrogram 账号模式）作为存储后端，可用标准 S3 客户端、AWS CLI、boto3 等直接对接。

**当前版本：** 见 [GitHub Releases](https://github.com/beihehele/Telezon-S3/releases) 与 GHCR 镜像标签。S3 能力见 [`docs/S3-COMPAT.md`](docs/S3-COMPAT.md)；认证与分享见 [`docs/AUTH-AND-SHARING.md`](docs/AUTH-AND-SHARING.md)（源码包内附带）。

[![CI](https://github.com/beihehele/Telezon-S3/actions/workflows/ci.yml/badge.svg)](https://github.com/beihehele/Telezon-S3/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/beihehele/Telezon-S3)](https://github.com/beihehele/Telezon-S3/releases)
[![GHCR](https://img.shields.io/badge/ghcr.io-beihehele%2Ftelezon--s3-blue)](https://github.com/beihehele/Telezon-S3/pkgs/container/telezon-s3)

> **账号模式部署必须使用单进程 / 单 worker**（Dockerfile 默认 `workers=1`）。不要在多个进程间共用同一条 `SESSION_STRING`，否则会导致 Telegram 会话冲突。

## 功能概览

- S3 协议：Put/Get/Head/Delete、ListBuckets、ListObjectsV2、CopyObject、DeleteObjects、分片上传、预签名 URL 等（以兼容文档为准）
- REST API：`/api/v1` 用户、桶、凭证、分享、回收站、Bearer 直传等
- 多凭证 RBAC：`readonly` / `readwrite`，可限定桶范围（`/api/v1/credentials`）
- 软删除与回收站：默认 DeleteObject 进回收站；`x-telezon-bypass-trash: true` 可硬删
- 公共桶、带密码的分享链接、SSE-C、可选磁盘缓存与 GC
- 出站代理：`TELEGRAM_PROXY`（SOCKS5/HTTP）

## 生产部署（无需克隆仓库）

在任意空目录准备 **`.env`** 与 **`docker-compose.yml`** 即可，应用与数据库均通过镜像运行。

### 1. 准备目录

```bash
mkdir telezon-s3 && cd telezon-s3
```

在 [Releases](https://github.com/beihehele/Telezon-S3/releases) 页面查看版本号，设 `VERSION`（不含前缀 `v`）。

**Linux / macOS：**

```bash
VERSION=x.y.z
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/.env.example"
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/docker-compose.yml"
curl -fsSLO "https://github.com/beihehele/Telezon-S3/releases/download/v${VERSION}/setup-telegram.sh"
cp .env.example .env
```

**Windows（PowerShell）：**

```powershell
$VERSION = "x.y.z"
Invoke-WebRequest -Uri "https://github.com/beihehele/Telezon-S3/releases/download/v$VERSION/.env.example" -OutFile ".env.example"
Invoke-WebRequest -Uri "https://github.com/beihehele/Telezon-S3/releases/download/v$VERSION/docker-compose.yml" -OutFile "docker-compose.yml"
Invoke-WebRequest -Uri "https://github.com/beihehele/Telezon-S3/releases/download/v$VERSION/setup-telegram.ps1" -OutFile "setup-telegram.ps1"
Copy-Item .env.example .env
```

完整步骤见 **[docs/DEPLOY.zh-CN.md](docs/DEPLOY.zh-CN.md)**。

### 2. 编辑 `.env`（先不要 `up -d`）

在 [my.telegram.org](https://my.telegram.org/apps) 申请后填入 `TELEGRAM_API_ID`、`TELEGRAM_API_HASH`；**`SESSION_STRING` 留空**；修改 `SECRET_KEY`、`MONGO_PASSWORD`、`INITIAL_ADMIN_PASSWORD` 等（见 [`.env.example`](.env.example) 分步注释）。

### 3. 首次 Telegram 登录（必须交互）

首次使用需在本机终端完成手机号 / 验证码 / 两步验证，无法在无 TTY 的后台自动完成：

```bash
export IMAGE_TAG=${VERSION:-latest}
docker compose pull
docker compose --profile setup run --rm setup
```

将输出的 `SESSION_STRING=...` 写入 `.env`。可选：按提示监听频道消息以获取 `CID`。

也可执行 Release 附带的 `setup-telegram.sh`（Linux/macOS）或 `setup-telegram.ps1`（Windows）。

### 4. 启动服务

```bash
docker compose up -d
```

服务地址：`http://localhost:8000`；就绪检查：`http://localhost:8000/api/health`（Mongo 与 Telegram 均为 ok 时返回 200）。Compose 中 **`.env` 的 `PORT` 表示宿主机映射端口**，容器内应用固定监听 **8000**。

### 5. 创建 S3 凭证

用 `INITIAL_ADMIN_*` 登录 REST API，在 `/api/v1/credentials` 创建访问密钥。

---

<details>
<summary>仅 Docker 运行应用（已有 Mongo）</summary>

若已有 MongoDB，可只拉应用镜像，在 `.env` 中设置 `DATABASE_URL` 后：

```bash
docker pull ghcr.io/beihehele/telezon-s3:${IMAGE_TAG:-latest}
docker run --rm -p 8000:8000 --env-file .env ghcr.io/beihehele/telezon-s3:${IMAGE_TAG:-latest}
```

镜像标签：`latest`、`x.y.z`、`x.y`、`sha-<commit>`（每次打 `v*` 标签发布）。

</details>

## API 文档

- Swagger UI：`http://localhost:8000/docs`
- S3 操作覆盖范围：[`docs/S3-COMPAT.md`](docs/S3-COMPAT.md)

## 环境要求

| 场景 | 要求 |
|------|------|
| 运行（Docker） | Docker、Docker Compose |
| 开发 | Python 3.12+、Poetry |
| 存储后端 | Telegram 账号（Pyrogram）、目标频道/群组；`TELEGRAM_API_ID` / `TELEGRAM_API_HASH` / `SESSION_STRING` |
| 元数据 | MongoDB |

> 运行时**仅支持账号模式（Pyrogram）**。`make setup_bot_storage` 为历史脚本，**不要**用于新部署。

## 配置说明

部署目录中应已有从 Release 复制的 `.env`（由 `.env.example` 改名而来）。需要参与源码开发时，再克隆仓库。

### 常用变量

```env
# 服务
PROJECT_NAME='Telezon S3'
PORT=8000
SECRET_KEY=请改为随机长字符串

# MongoDB（Compose 中 app 会使用 DATABASE_URL 指向 db 服务）
MONGO_HOST=localhost
MONGO_PORT=27017
MONGO_USER=admin
MONGO_PASSWORD=你的密码
DATABASE_NAME=TelezonS3

# Telegram（账号模式）
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
SESSION_STRING=
# 留空直至 docker compose --profile setup run --rm setup 生成
CID=
# 默认存储频道/群；未配置时启动会记录警告，上传前请填写或通过 setup 获取
# BOT_TOKEN=
# TELEGRAM_PROXY=socks5://user:pass@127.0.0.1:1080

# 首次启动自动创建的管理员（登录 REST API 后发凭证）
INITIAL_ADMIN_USER=admin
INITIAL_ADMIN_PASSWORD=请修改默认密码
```

更多项（上传大小、限流、GC、回收站保留、分享防爆破等）见 Release 附带的 `.env.example`。

### 初始管理员

设置 `INITIAL_ADMIN_USER` 与 `INITIAL_ADMIN_PASSWORD` 后，Mongo 初始化时会创建首个管理员用户；**默认桶名与用户名相同**。请通过 REST 登录并创建 S3 访问密钥（`/api/v1/credentials`），不要在生产环境保留弱密码。

## 本地开发（需克隆仓库）

```bash
git clone https://github.com/beihehele/Telezon-S3.git
cd Telezon-S3
poetry install
make dev
```

生成 Telegram 账号会话（推荐）：

```bash
make setup_account_storage
```

常用 Make 目标：

- `make dev` — 开发模式启动  
- `make run` — 生产风格启动（单 worker）  
- `make format` — ruff 格式化  
- `make setup_account_storage` — 配置 Pyrogram 会话  
- `make export` — 导出 `requirements.txt`

运行测试：

```bash
poetry run pytest
```

## 使用示例

### boto3

```python
import boto3

s3 = boto3.client(
    "s3",
    aws_access_key_id="你的 AccessKey",
    aws_secret_access_key="你的 SecretKey",
    endpoint_url="http://localhost:8000",
)

s3.upload_file("local.txt", "桶名", "对象键.txt")
s3.download_file("桶名", "对象键.txt", "下载.txt")
```

### 项目自带脚本

```bash
poetry run python upload_file.py \
  --access-key-id ... --secret-key ... \
  --bucket-name 桶名 --input-path local.txt --output-path remote.txt

poetry run python download_file.py \
  --access-key-id ... --secret-key ... \
  --bucket-name 桶名 --input-path remote.txt --output-path local.txt
```

## Windows 可执行文件（测试 / 内网）

可使用 PyInstaller 从**源码包**打成单目录包（需克隆或解压 Release 源码归档）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-exe.ps1
```

产物：`dist\Telezon-S3\Telezon-S3.exe`（需连同同目录下 `_internal` 等文件一起拷贝）。

1. 编辑 `dist\Telezon-S3\.env`（Mongo 须可达；可用上文 Compose 仅启动 `db`：`docker compose up -d db`）  
2. 运行 `.\Telezon-S3.exe`  
3. 浏览器打开 `http://127.0.0.1:8000/docs`

自动冒烟（依赖 Mongo 已启动）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test-exe.ps1
```

说明：exe 需自行从源码构建（见 `scripts/build-exe.ps1`）；日常生产环境推荐使用 GHCR 镜像部署。

## 贡献

欢迎通过 Issue 讨论后再提交 PR。

## 规模与限制

Telezon S3 适合个人或小团队、低频/中等流量的对象存储场景。Telegram 对频率、单文件大小等有平台侧限制；高并发、大流量对外分发请选用对象存储专用方案（如 S3、MinIO 等）。

## 许可证

MIT

# 本地开发与测试

与 CI（`.github/workflows/ci.yml`）对齐的约定命令，便于在合入前自测。

## 依赖

- **Python 3.12**（与 CI 一致；3.13+ 在 Windows 上可能缺少部分 wheel，需 MSVC 编译）
- **Poetry**（推荐）或 `pip install -r requirements.txt`
- 控制台改动时：**Node 20** + `console/package-lock.json`

```bash
poetry install
# 或：poetry export -f requirements.txt -o requirements.txt --without-hashes && pip install -r requirements.txt
pip install pytest pytest-asyncio httpx aiosqlite cryptography socksio "httpx[socks]"
```

## 全量 pytest（与 CI 相同环境变量）

测试使用内存 SQLite，**不需要**真实 MySQL / Telegram。`tests/conftest.py` 会在导入时设置默认环境变量（含 `SECRET_KEY`、`DATABASE_URL`），多数情况下在仓库根目录直接运行即可。

### Linux / macOS / Git Bash

```bash
export PROJECT_NAME=telezon-test
export PORT=8000
export SECRET_KEY=telezon-ci-secret-key-16b
export DATABASE_URL=sqlite+aiosqlite:///:memory:
export BOT_TOKEN=0:test
export CID=123
export TELEGRAM_API_ID=1
export TELEGRAM_API_HASH=hash
export SESSION_STRING=session

pytest -q
# 或：poetry run pytest -q
```

### Windows PowerShell

```powershell
$env:PROJECT_NAME = "telezon-test"
$env:PORT = "8000"
$env:SECRET_KEY = "telezon-ci-secret-key-16b"
$env:DATABASE_URL = "sqlite+aiosqlite:///:memory:"
$env:BOT_TOKEN = "0:test"
$env:CID = "123"
$env:TELEGRAM_API_ID = "1"
$env:TELEGRAM_API_HASH = "hash"
$env:SESSION_STRING = "session"

python -m pytest -q
```

**Windows 提示：**

- 若 `python` 指向 `WindowsApps\python.exe` 且无法运行，用 `py -0p` 查看已装版本，或直接用安装目录下的 `python.exe`（例如 `C:\Users\<你>\AppData\Local\Python\bin\python.exe`）。
- 首次 `pip install` 若报 **Microsoft Visual C++ 14.0**，请安装 [Build Tools for Visual Studio](https://visualstudio.microsoft.com/visual-cpp-build-tools/)（勾选「使用 C++ 的桌面开发」），或改装 **Python 3.12** 以使用预编译 wheel。
- 依赖装好后，统一用 **`python -m pytest -q`**（不必把 Scripts 加入 PATH）。

子集示例：`python -m pytest tests/api/test_objects_rest.py -q`

## Web 控制台

```bash
cd console
npm ci
npm run build          # 类型检查 + 生产构建
npm run build:app      # 复制到 app/static/console/（本地 ENABLE_CONSOLE=1 时用）
```

后端挂载静态资源：`ENABLE_CONSOLE=1`，且存在 `app/static/console/`。

### Playwright（可选）

与 CI 相同的最小冒烟（仅登录页，无需后端）：

```bash
cd console
npm ci && npm run build
npx playwright install chromium
npx vite preview --host 127.0.0.1 --port 4173 &
# 等待 preview 就绪后：
CONSOLE_E2E_BASE=http://127.0.0.1:4173/console/ npx playwright test --grep "login page loads"
```

完整 E2E（登录 → 文件页）需运行中的 API，并设置 `CONSOLE_E2E_USER`、`CONSOLE_E2E_PASSWORD`；见 `console/README.md`。

### 部署后 HTTP 冒烟（NAS / 预发布）

对**已运行的实例**做 API 黑盒检查（健康、控制台挂载、登录、presign 小文件往返、可选 413/Range）。**不进 CI**（需真实服务与账号）。

```powershell
$env:TELEZON_SMOKE_BASE = "http://你的主机:8088"
$env:CONSOLE_E2E_USER = "admin"
$env:CONSOLE_E2E_PASSWORD = "你的密码"
# 可选：TELEZON_SMOKE_TIMEOUT、TELEZON_SMOKE_TG_TIMEOUT（大对象 Range 回源）
python scripts/smoke_deploy.py
```

与 Playwright（`console/e2e/smoke.spec.ts`）互补：脚本覆盖 API 与 content 代理；Playwright 覆盖登录页与文件壳。手工项见 [`docs/CONSOLE-VERIFY.zh-CN.md`](CONSOLE-VERIFY.zh-CN.md)。

## 相关文档

- 路线图与勾选进度：[`docs/ROADMAP.zh-CN.md`](ROADMAP.zh-CN.md)
- NAS 手工验收：[`docs/CONSOLE-VERIFY.zh-CN.md`](CONSOLE-VERIFY.zh-CN.md)
- 发布与 CI 说明：[`docs/RELEASE.md`](RELEASE.md)

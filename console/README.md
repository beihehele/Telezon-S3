# Telezon Web Console

Vue 3 + Vite + Element Plus。构建产物用于 FastAPI `/console/`。

## 开发

```bash
npm install
npm run dev
```

Vite 将 `/api` 代理到 `http://127.0.0.1:8000`（需本地已启动后端）。

## 发布到后端静态目录

```bash
npm run build:app
```

输出到仓库根目录 `app/static/console/`。Docker 镜像构建会在多阶段 Dockerfile 内执行 `npm run build` 并复制 `dist/`。

## 相关文档

- 路线图：[`docs/ROADMAP.zh-CN.md`](../docs/ROADMAP.zh-CN.md)
- 本地 pytest / E2E：[`docs/DEVELOP.zh-CN.md`](../docs/DEVELOP.zh-CN.md)

## E2E（可选）

```bash
# 后端 ENABLE_CONSOLE=1 已运行
export CONSOLE_E2E_USER=...
export CONSOLE_E2E_PASSWORD=...
npx playwright install chromium
npm run test:e2e
```

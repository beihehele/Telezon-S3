# Web 控制台验收清单（NAS / 预发布）

在部署升级后，建议在同一台将部署的机器上走一遍（`ENABLE_CONSOLE=1`，`PUBLIC_BASE_URL` 与浏览器访问地址一致）。

**自动化（可选）：** 设置 `TELEZON_SMOKE_BASE`、`CONSOLE_E2E_USER`、`CONSOLE_E2E_PASSWORD` 后运行 `python scripts/smoke_deploy.py`；浏览器 UI 用 `cd console && npx playwright test`（需 `CONSOLE_E2E_BASE`）。详见 [`docs/DEVELOP.zh-CN.md`](DEVELOP.zh-CN.md)。

## 环境

- [ ] `.env`：`SECRET_KEY`、`MYSQL_*`、`SESSION_STRING`、`CID`（或桶级 `telegram_chat_id`）已配置
- [ ] `ENABLE_CONSOLE=1`
- [ ] `PUBLIC_BASE_URL=https://你的域名`（无尾斜杠；用于预签名 Host）
- [ ] 可选：`MEDIA_TICKET_MAX_SECONDS=900`
- [ ] 镜像含控制台静态资源（Release 构建）或本地执行过 `cd console && npm run build:app`
- [ ] 打开 `https://<域名>/console/#/login` 无 404

## 认证

- [ ] 登录：已有用户 `POST /api/auth/login` 对应表单成功
- [ ] `ALLOW_SIGNUP`：公网建议 `0`；`1` 时 `#/register` 与 `GET /api/auth/config` 一致
- [ ] 退出后需重新登录

## 文件（桶主）

- [ ] 桶下拉与 URL `?bucket=` 一致
- [ ] 列表：前缀、文件夹、`delimiter=/` 正常
- [ ] 小文件上传（presign PUT）成功并出现在列表
- [ ] 下载（presign GET）可打开
- [ ] 重命名、**勾选多项后批量删除**
- [ ] 大文件（>80MB 或你环境阈值）走分片上传进度条
- [ ] 图片预览（JWT 或 presign）
- [ ] 大体积 txt/json（>8MB）：预览应自动新开标签页（预签名）；若被拦截则对话框内显示链接
- [ ] 视频预览：`content-ticket` + 拖动进度条（Range）；慢时可切「预签名预览」

## 分享 / 密钥 / 桶

- [ ] 创建分享 → 复制 `/share/{token}` → 匿名浏览器可下载（有密码则验证）
- [ ] 子账号密钥：只读/读写、限定桶
- [ ] 桶设置：公开读、TG chat/topic 保存

## 回收站

- [ ] 删除后进回收站；恢复；永久删除

## Admin（仅管理员）

- [ ] 用户列表、新建、改邮箱/角色/密码、删除（不能删自己）
- [ ] **不能**在控制台浏览其他用户的对象列表（应 403）

## API 健康

- [ ] `/api/health` 数据库与 Telegram 为 ok（或已知降级原因）

## 回归（S3 客户端）

- [ ] S3 Browser / rclone：`ListObjects`、`PutObject`、大文件 MPU 仍正常（与 0.11.2 行为一致）

---

失败时请记录：请求路径、HTTP 状态、响应体片段、容器日志（勿贴 `SECRET_KEY` / `SESSION_STRING`）。

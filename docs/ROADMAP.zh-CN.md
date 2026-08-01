# 版本路线图（0.12 — 0.14）

> 详细设计与任务拆解在本地 `docs/superpowers/`（**未纳入 git**，见 `.gitignore`）。本文档为仓库内可跟踪的摘要。

**当前稳定线：** `v0.14.0`（Web 控制台 + JWT 对象 REST + media ticket / Range）。

**本文件记录：** 0.12 / 0.13 / 0.14 合入 **v0.14.0**（2026-08-01）。

---

## 进度快照（v0.14.0，2026-08-01）

| 版本 | 状态 | 要点 |
|------|------|------|
| **0.12** | 基本完成 | JWT 对象 REST、batch-delete、`UserPublic`、分享列表、Vue 控制台 MVP、Docker 多阶段、`ENABLE_CONSOLE` |
| **0.13** | 大部分完成 | MPU 上传 UI、暗色/移动布局、分享/重命名/Admin 用户/子账号密钥 UI、Playwright 冒烟 + CI |
| **0.14** | 核心已做 | 分片 Range 按需读、`GET …/content` + **media ticket**、MP4 `moov` 探测缓存、presign POST+query（MPU） |

**预览鉴权：** 视频使用 `POST …/content-ticket` → `GET …/content?media_token=`（非登录 JWT）。

**约束（仍有效）：** Admin **不能**浏览他人对象；控制台 zh-CN。

**本地自测：** 全量 pytest 与 CI 环境变量见 [`docs/DEVELOP.zh-CN.md`](DEVELOP.zh-CN.md)。

---

## v0.12.0 — Web 控制台 + JWT 对象 REST

**目标：** 浏览器网盘式管理（Vue 3），不替代 S3 客户端。

### 后端（A）

- [x] 对象 REST：列表、元数据、删除、**batch-delete**、重命名
- [x] `GET …/content`（Bearer；0.14 扩展 media token）
- [x] `UserPublic`；`GET /api/v1/shares`（admin 可选 `?owner=`）
- [x] `ENABLE_CONSOLE` + 静态挂载 `/console/`
- [x] `HTTPException` 保留真实 HTTP 状态码

### 前端（B）

- [x] 登录、注册（受 `ALLOW_SIGNUP` 控制）
- [x] 桶选择、文件浏览、presign 上传/下载/预览
- [x] 回收站、分享、子账号密钥、桶设置
- [x] Admin 用户管理（控制台）

### 打包

- [x] Dockerfile 多阶段构建 SPA → `app/static/console/`

**规格：** `docs/superpowers/specs/2026-08-01-web-console-design.md`  
**计划：** `docs/superpowers/plans/2026-08-01-web-console-0.12.md`

---

## v0.13.0 — 控制台打磨

- [x] Multipart 上传 UI（presign + S3 MPU）
- [x] Admin 用户 CRUD、分享创建/复制链接、对象重命名
- [x] 暗色主题、基础移动端布局
- [x] `ALLOW_SIGNUP` + `GET /api/auth/config`；关闭时隐藏注册
- [x] Playwright：登录页冒烟；CI 在 `vite preview` 上跑 `login page loads`
- [ ] Playwright：登录 → 上传 → 预览（需运行后端 + 账号或 mock）
- [ ] NAS 实机：大文件 MPU presign 全链路（Complete / 失败回退策略）

---

## v0.14.0 — 媒体投递 / Range 优化

- [x] MPU 对象 **按 Range 只拉必要 part**（`load_blob_byte_range`）
- [x] `GET …/content` + **media ticket**（`POST …/content-ticket`；与 presign 并存）
- [x] MP4 `moov` 索引缓存（头/尾探测）
- [x] Presign **POST** + `extra_query`（浏览器 MPU）
- [ ] NAS 实机：长视频 Range 拖动、multipart 对象 REST 预览

**规格（备忘）：** `docs/superpowers/specs/2026-08-01-media-range-index-design.zh-CN.md`

---

## 跨版本 backlog（未排期）

| 项 | 说明 |
|----|------|
| 跨桶 Copy → 论坛 **Topic** | `forward_messages` 不进 `telegram_topic_id` |
| SSE-C Put 流式加密 | 当前加密仍需整段明文 |
| 真 SigV4 流式上传集成测 | 补 S3 Browser 级回归 |
| E2E 上传→预览全链路 | 需 NAS/CI 与 Telegram 或 mock 存储 |

**验收清单：** [`docs/CONSOLE-VERIFY.zh-CN.md`](CONSOLE-VERIFY.zh-CN.md)

---

## 历史阶段文档（0.2 — 1.0，已交付）

`docs/superpowers/specs/` 中的早期里程碑；能力大多已并入 `0.9`—`0.11.x`。

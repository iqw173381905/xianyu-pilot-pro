# 精简部署说明（xypro.mrcc.top，2026-10-21 上线）

在 2C2G 服务器上跑 9 个服务。商品编辑/改价/上下架走
user-web → core-api → automation → 闲鱼 MTOP 接口，不依赖爬虫；
爬虫三件套 2026-10-21 晚为滑块求解补部署（见下文专节）。

## 组成（docker-compose.slim.yml）

| 服务 | 说明 | 内存上限 |
| --- | --- | --- |
| mysql | 业务库 xianyu_assistant_admin | 384m |
| redis | 缓存 | 80m |
| backend | core-api（Java），仅绑 127.0.0.1:18080 | 448m |
| automation | automation-service（Python） | 320m |
| automation-worker | 后台任务 | 256m |
| user-web | 前端，绑 0.0.0.0:5174 | 64m |
| crawler-postgres | 爬虫库 xianyu_crawler | 128m |
| crawler-service | 滑块求解 API（:3001，仅内网） | 512m |
| crawler-worker | 滑块求解执行（Chrome） | 640m |

六件套实测约 780MB，爬虫三件套空闲再加约 270MB。仍砍掉的：admin-web。
代价：没有商机挖掘/对标跟卖/工作流铺货；加账号走 Cookie 导入。

## 滑块求解（爬虫三件套）

- 镜像用 `apps/crawler-service/Dockerfile.slim`：官方版基于
  mcr.microsoft.com/playwright 镜像（约 950MB，国内拉取几乎不动），
  slim 版改用 Docker Hub 官方 node:24.18.0-bookworm-slim（走腾讯镜像源）
  + 系统 google-chrome-stable。代码在 Linux 下所有浏览器启动都走
  channel:'chrome'，功能一致；仅扫码登录（qrLoginSolver 的无 channel
  启动）没有自带 Chromium 时不可用，本部署走 Cookie 导入，不受影响。
  浏览器并发已降为 1（CRAWLER_BROWSER_CONCURRENCY）。
- `.env` 需额外：CRAWLER_DB_PASSWORD、CRAWLER_CORS_ALLOWED_ORIGINS
  （后者必填一个显式 HTTPS 源，如 https://xypro.mrcc.top，
  否则生产模式拒绝启动）。
- **首次启动前必须跑一次官方维护迁移**（生产模式服务只校验 schema、
  不自动建表，不跑会报“数据库迁移失败，生产环境拒绝启动”）：
  `docker compose -f docker-compose.slim.yml run --rm -e MIGRATION_MAINTENANCE_APPROVED=true -e RELEASE_ID=slim-20261021 -e MIGRATION_MANIFEST_SHA256=fcf560641f97ea21b5162e6aef0487caf196ee68774475e4b6b8424a0d2586c9 crawler-service node dist/migrate.js`
  （RELEASE_ID 换成自己的发布号，SHA256 必须与镜像内 src/migrate.ts 的
  REVIEWED_MANIFEST_SHA256 一致。）
- 求解链路：详情/订单等深接口被闲鱼 FAIL_SYS_USER_VALIDATE 时不会自动
  求解；要在账号页点“手动滑块求解”（或调 POST /captcha/handle）。
  求解前有预校验：排除表 → 账号状态 → **Cookie 会话有效性**——
  Cookie 会话已过期（SESSION_EXPIRED）时求解会被直接拒绝，
  必须先重新导入一份新鲜 Cookie，滑块解得再好也救不了过期会话。

## 部署步骤

1. 准备 `.env`（不要提交到仓库），键名清单：
   MYSQL_ROOT_PASSWORD、MYSQL_APP_USER、MYSQL_APP_PASSWORD、REDIS_PASSWORD、
   INTERNAL_API_TOKEN、COOKIE_CRYPTO_SECRET、ADMIN_JWT_SECRET、JWT_SECRET、
   API_KEY_CRYPTO_SECRET、OPS_METRICS_TOKEN、OPEN_SOURCE_BRIDGE_TOKEN、
   DATA_SYNC_API_TOKEN、COMMERCIAL_BACKEND_ACCESS_TOKEN、ADMIN_SEED_ENABLED、
   USER_CORS_ALLOWED_ORIGINS、CRAWLER_DB_PASSWORD、CRAWLER_CORS_ALLOWED_ORIGINS
2. `docker compose -f docker-compose.slim.yml build && docker compose -f docker-compose.slim.yml up -d`
3. **空库首次启动后必须补表结构**：见 `schema-patches.sql`（不补会持续报 Unknown column）。
4. 首次用种子管理员 admin / 123456 登录，立即改密码，然后把
   `ADMIN_SEED_ENABLED` 改为 false 并重建 backend（`docker compose up -d backend`；
   注意 `docker restart` 不会重读 .env）。
5. 自用免会员门禁（可选）：全部功能门禁只看 `sys_user.vip_level`
   （0 普通 / 1 VIP / 2 SVP，后端 FeatureSwitchService 与 automation 的
   captcha 优先级共用此字段）。自部署单用户场景直接执行
   `UPDATE sys_user SET vip_level=2 WHERE id=1;` 即全功能放行，无到期时间。
   滑块求解组件已补部署（见上文专节），门禁放开后可直接使用。

## 三个已踩过的坑

1. **CORS**：`USER_CORS_ALLOWED_ORIGINS` 必须包含前端的实际访问源
   （如 `https://xypro.mrcc.top`），否则浏览器登录被 403 拦截
   （前端显示“暂无权限执行此操作”）；用不带 Origin 的 curl 测登录测不出来。
2. **协议链接是构建期变量**：user-web 的 Dockerfile 已注入
   `VITE_TERMS_URL=/legal/terms.html`、`VITE_PRIVACY_URL=/legal/privacy.html`，
   页面文件在 `apps/user-web/public/legal/`。不配这两个值，登录页会以
   “用户协议或隐私政策链接未配置”拦住登录。
3. **Dockerfile 构建补丁**：core-api 加了 `MAVEN_OPTS=-Xmx640m` 防小内存机
   构建 OOM；user-web 用 npmmirror 源加速。

## 对外访问

正式入口 https://xypro.mrcc.top ：DNSPod A 记录指向服务器，证书由 acme.sh
（dns_dp 验证）签发自动续期，总代理 nginx 加 443 块反代到 172.17.0.1:5174，
并已为 SSE 关掉代理缓冲、放宽上传体积到 32m。

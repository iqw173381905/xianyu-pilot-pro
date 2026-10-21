# 精简部署说明（xypro.mrcc.top，2026-10-21 上线）

在 2C2G 服务器上只跑 6 个服务，砍掉整条爬虫线。商品编辑/改价/上下架走
user-web → core-api → automation → 闲鱼 MTOP 接口，不依赖爬虫。

## 组成（docker-compose.slim.yml）

| 服务 | 说明 | 内存上限 |
| --- | --- | --- |
| mysql | 业务库 xianyu_assistant_admin | 384m |
| redis | 缓存 | 80m |
| backend | core-api（Java），仅绑 127.0.0.1:18080 | 448m |
| automation | automation-service（Python） | 320m |
| automation-worker | 后台任务 | 256m |
| user-web | 前端，绑 0.0.0.0:5174 | 64m |

全栈实测约 780MB。砍掉的：crawler-service、crawler-worker、crawler-postgres、admin-web。
代价：没有商机挖掘/对标跟卖/工作流铺货/滑块自动求解；加账号走 Cookie 导入。

## 部署步骤

1. 准备 `.env`（不要提交到仓库），键名清单：
   MYSQL_ROOT_PASSWORD、MYSQL_APP_USER、MYSQL_APP_PASSWORD、REDIS_PASSWORD、
   INTERNAL_API_TOKEN、COOKIE_CRYPTO_SECRET、ADMIN_JWT_SECRET、JWT_SECRET、
   API_KEY_CRYPTO_SECRET、OPS_METRICS_TOKEN、OPEN_SOURCE_BRIDGE_TOKEN、
   DATA_SYNC_API_TOKEN、COMMERCIAL_BACKEND_ACCESS_TOKEN、ADMIN_SEED_ENABLED、
   USER_CORS_ALLOWED_ORIGINS
2. `docker compose -f docker-compose.slim.yml build && docker compose -f docker-compose.slim.yml up -d`
3. **空库首次启动后必须补表结构**：见 `schema-patches.sql`（不补会持续报 Unknown column）。
4. 首次用种子管理员 admin / 123456 登录，立即改密码，然后把
   `ADMIN_SEED_ENABLED` 改为 false 并重建 backend（`docker compose up -d backend`；
   注意 `docker restart` 不会重读 .env）。
5. 自用免会员门禁（可选）：全部功能门禁只看 `sys_user.vip_level`
   （0 普通 / 1 VIP / 2 SVP，后端 FeatureSwitchService 与 automation 的
   captcha 优先级共用此字段）。自部署单用户场景直接执行
   `UPDATE sys_user SET vip_level=2 WHERE id=1;` 即全功能放行，无到期时间。
   注意：滑块“求解”本身由 crawler-service 执行，精简版未部署该组件，
   门禁放开后点求解会提示服务不可达，需要时再单独拉起爬虫组件。

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

-- xianyu-pilot-pro 精简部署：全新空库首次启动后必须补打的表结构补丁
-- 背景：automation-service 会先建表，导致 core-api 的 CREATE TABLE IF NOT EXISTS 空转，
--       一批列只有 backend 的 DDL / V*.sql 迁移里有、运行时永远不会自动补，缺列会让
--       定时任务与部分接口持续报 Unknown column。
-- 2026-10-21 首次部署时共补齐 39 列，涉及表：
--   sys_user、xianyu_trade_order、payment_order、delivery_text_source、
--   delivery_record、ai_cs_kb_category、ai_cs_learned_kb、xianyu_account_health_snapshot
-- 完整列清单见同目录 schema-reference.txt（生产库 information_schema 快照）。
-- 重建时的做法：把 backend 的全部 CREATE TABLE DDL 与 db/migration/V*.sql 中所有
-- ADD COLUMN 与目标库 information_schema 做 diff，缺什么补什么；下面三条是当时
-- 需要手工处理的特殊项（不在自动 diff 的 ADD COLUMN 里）：

-- 1) automation 先建的表缺 snapshot_time（backend 按此列排序/查询）
ALTER TABLE `xianyu_account_health_snapshot`
  ADD COLUMN `snapshot_time` DATETIME NULL DEFAULT CURRENT_TIMESTAMP;

-- 2) security_version 必须有默认值，否则新注册/种子用户写入失败
ALTER TABLE `sys_user`
  MODIFY COLUMN `security_version` BIGINT NOT NULL DEFAULT 1;

-- 3) 迁移文件里该列的 DEFAULT 引号被转义写坏，按正确值补
ALTER TABLE `ai_cs_learned_kb`
  ADD COLUMN `source_type` VARCHAR(16) NOT NULL DEFAULT 'ai';

-- 4) 地址字典表：执行 apps/core-api/src/main/resources/db/migration/
--    V1.12__add_china_address_dict.sql（只有建表语句，数据按需同步）。

-- ============================================================
-- automation 侧缺口（2026-10-21 晚补，滑块求解链路实测踩出）
-- automation-service/migrations/ 的迁移在官方部署里另有执行路径，
-- 精简部署不会自动跑；与滑块相关的以下文件需手工执行一次
-- （mysql --force 灌入，重复列/已存在报错可忽略）：
--   V1.8、V1.9、V1.10、V1.14、V1.15、V1.16、V1.17、V1.24
-- 其中 V1.28 用了 MariaDB 的 IF NOT EXISTS 语法，MySQL 8 跑不了，
-- 等价手工 SQL 如下：
ALTER TABLE `xianyu_captcha_solve_record`
  ADD COLUMN `proxy_source` VARCHAR(32) NOT NULL DEFAULT '';
CREATE INDEX `idx_xcsr_proxy_source_created`
  ON `xianyu_captcha_solve_record` (`proxy_source`, `created_at`);
CREATE INDEX `idx_xcsr_proxy_result`
  ON `xianyu_captcha_solve_record` (`proxy_source`, `result`, `created_at`);

-- 求解记录插入语句不给 priority/failure_reason 赋值，这两列若是
-- NOT NULL 且无默认值，create_captcha_solve_record 会持续
-- OperationalError、记录落不了库：
ALTER TABLE `xianyu_captcha_solve_record` ALTER COLUMN `priority` SET DEFAULT 0;
ALTER TABLE `xianyu_captcha_solve_record` ALTER COLUMN `failure_reason` SET DEFAULT '';

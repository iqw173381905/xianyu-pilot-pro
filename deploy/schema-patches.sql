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

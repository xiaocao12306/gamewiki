# 数据采集骨架验证指引

本指引帮助开发/测试验证 MVP 阶段的埋点链路是否通路——客户端缓存上报、后端写库、手动观测。

## 组件确认

- **客户端**
  - `AnalyticsManager`（`core/analytics.py`）：维护内存队列，支持定时/手动 flush。
  - `BackendClient.post_events`：向 `/api/v1/events` POST 批量事件。
  - 典型触发：`assistant_integration` 中 `_track_event`、模型调用埋点、fallback 相关事件。
- **后端**
  - `POST /api/v1/events`（`app/api/routes/events.py`）：写入 `events` 表，限制每批 100 条。
  - `Event` 模型（`app/models/entities.py`）：字段 `name`、`properties`（JSON）、`created_at`。

## 手动验证步骤

1. **环境准备**
   - 启动后端（FastAPI + PostgreSQL），确保 `.env` 中 `DATABASE_URL`、`JWT_SECRET_KEY` 等配置正确。
   - 运行客户端桌面应用，并保证 `settings.json` 中已配置 API Key、后端地址。
2. **触发事件**
   - 在助手界面执行一次 AI 查询（可在 limited mode 或本地模式）。
   - 期望客户端日志出现 `AnalyticsManager 启动`、以及 `成功上报 X 条事件` 等信息。
3. **观察后端**
   - 后端日志应出现 `POST /api/v1/events 200`。
   - 可在数据库中执行
     ```sql
     select name, properties, created_at from events order by created_at desc limit 10;
     ```
     确认有 `deepseek_call_success`、`model_fallback_triggered` 等事件。
4. **异常兜底**
   - 手动断网或停止后端后再触发一次事件，客户端日志应提示 `事件上报失败` 并在重试后重新入队。
   - 恢复后端，调用 `AnalyticsManager.flush()`（例如重启客户端或关闭时自动调用）确认队列清空。

## 既有限制 / TODO

- 当前队列默认上限 50，后续如需更高吞吐量需引入批量压缩或本地落盘。
- 未对事件字段做 schema 校验，前端需自行约束 key 格式；若未来有 BI 需求建议补充枚举或约束。
- 没有实时 dash，需依赖数据库查询或额外分析工具。

## 快速自检清单

- [ ] 客户端启动日志包含 `AnalyticsManager 启动`。
- [ ] 激活一次 AI 请求后，客户端日志出现 `成功上报` 行。
- [ ] 后端数据库 `events` 表能查询到对应记录。
- [ ] 关闭客户端时调用 `AnalyticsManager.shutdown()`，日志无异常。

完成以上步骤即可认为“数据采集骨架”打通。

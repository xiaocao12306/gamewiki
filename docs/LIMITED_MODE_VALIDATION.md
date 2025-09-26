# Limited Mode & Cloud Proxy 验证指引

本指引描述如何在 **limited mode**（无本地 Gemini Key，走云端代理）下完成关键场景的手动验证，确保本地检索、云端预处理与回退逻辑工作正常。

## 前置条件
- 后端 `backend` 服务与数据库已启动，可访问 `/api/v1/chat`、`/api/v1/events`。
- 客户端以 limited mode 运行（在启动参数或配置中启用；默认缺少 `GEMINI_API_KEY` 时会进入该模式）。
- 向量库数据已生成并位于 `ai/vectorstore` 目录，且与测试所选游戏匹配。
- 日志窗口：
  - 客户端日志，可看到 `🔁 Limited mode context prepared…` 等输出。
  - 后端日志，可看到 `收到携带上下文的聊天请求…`、`DeepSeek 请求成功…` 等信息。

## 场景一：携带上下文成功
1. 在游戏窗口或模拟窗口中选择已构建向量库的游戏（例如 *Don't Starve Together*）。
2. 在客户端输入攻略类问题，例如：`冬天怎么取暖`。
3. 观察日志：
   - 客户端出现 `🔁 Limited mode context prepared... snippets=…`，并打印被注入的系统提示长度和标题。
   - 后端输出 `收到携带上下文的聊天请求 system_total=2 extra_context=1 ...`。
4. 预期结果：
   - `/api/v1/chat` 返回 200 且模型答复显示在 UI 中。
   - `/api/v1/events` 记录成功的埋点回传。

## 场景二：无上下文回退 Wiki
1. 制造“无上下文”条件，可选方式：
   - 临时重命名对应游戏的向量库配置文件；或
   - 切换到尚未构建向量库的游戏窗口。
2. 输入同类问题。
3. 预期日志：
   - 客户端无 `context prepared`，改为 `📭 No context snippets available…`。
   - `_fallback_to_wiki` 打印并提示“📭 暂未找到本地参考资料…”。
   - 后端仍会记录一次 `/api/v1/chat` 调用（若无上下文直接跳 Wiki 则不发起），并上报 `model_fallback_triggered`，`reason=no_context`。
4. 预期结果：UI 自动切换到 Wiki 搜索页，无模型答复。

## 场景三：云端异常回退 Wiki
1. 让 `/api/v1/chat` 调用失败，可临时关闭网络或停止 DeepSeek 代理。
2. 输入攻略问题，保持有向量库可用。
3. 预期日志：
   - 客户端 `🔁 Limited mode context prepared` 后紧接着出现 `Cloud chat request failed` 并触发 `_fallback_to_wiki`。
   - 后端 `DeepSeek 请求失败` 或 HTTP 异常，同时仍上报 `model_fallback_triggered`，`reason=cloud_fallback`。
4. 预期结果：UI 提示“云端模型暂不可用…”，并自动跳转 Wiki。

## 验收要点
- 三个场景都需核对客户端与后端日志，确保埋点事件触发：`deepseek_call_*`、`model_fallback_triggered`。
- 确认 `@Task/deepseek_model_integration.md` 手动测试记录与本指引保持一致，后续回归可直接引用此文档。
- 如需将流程展示给后端/运营，可截取日志片段及界面截图，附加在该文档或相关周报中。

# 第七阶段：在线 AI Provider 接入实施设计

- 创建日期：2026-11-05。
- 状态：已完成；第七阶段专项 10 项通过，全量 119 项通过，DashScope 真实冒烟与真实浏览器联调通过。
- 技术边界：继续使用 FastAPI、SQLite、原生 HTML／CSS／JavaScript；新增一个 OpenAI 兼容的在线 Provider 客户端，不引入 SDK 或前端框架。

本阶段把确定性 `SimulatedModel` 扩展为可切换的在线模型：自由输入优先交给在线模型解析为合法行动，失败时回退本地确定性匹配；叙事只根据已提交事实生成文字。世界事实、骰点、权限、认知与回放仍由程序掌握。

## 1. 已确认决策

1. 在线模型参与意图解析与叙事；意图不合法或调用失败时回退 `SimulatedModel`。
2. 叙事调用失败沿用现有契约：行动进入 `narrative_pending`，玩家手动重试；已提交事实不变。
3. 调用元数据只写服务端日志与健康接口，不扩展审计 v3、不改既有审计和回放测试。
4. 优先使用 `.env` 中的 DashScope；Provider／模型选择由 `AI_CURRENT_PROVIDER`、`AI_CURRENT_MODEL` 决定。

## 2. 配置契约

`.env` 保持用户现有格式，不新增必填项：

- `AI_CURRENT_PROVIDER`、`AI_CURRENT_MODEL`：当前 Provider 与模型编号。
- `AI_PROVIDER_<n>_NAME／BASE_URL／API_KEY／TIMEOUT_SECONDS／MAX_RETRIES／MAX_OUTPUT_TOKENS`。
- `AI_MODEL_<n>_<m>_NAME`：模型名。

读取规则：

1. 进程环境变量优先于 `.env`，便于测试和临时覆盖。
2. 缺少当前 Provider 编号时返回 `None`，应用回退 `SimulatedModel`，保证无 `.env` 环境仍可运行。
3. 编号非法、`BASE_URL` 非 http(s)、有在线 Provider 却缺 `API_KEY`、缺模型名时，明确报错且错误信息不含密钥。
4. 超时限制在 5—600 秒，重试限制在 0—5 次；单次输出令牌由调用方另行收紧，不直接使用 131072 上限。

## 3. 模型职责

### 3.1 意图解析

- 输入只有玩家文本和当前地点合法行动目录（编号、标签、别名、倾向、是否掷骰、修正）。
- 要求只输出 JSON：`{"kind":"case_action","action_id":"..."}` 或 `{"kind":"no_match"}`。
- 只接受目录内 `action_id`；标签、倾向、掷骰与修正一律从程序目录读取，不信任模型返回值。
- `no_match`、非法 JSON、未知行动、超时、429、5xx 或鉴权失败时回退本地 `SimulatedModel`，并记录脱敏原因。
- 回退不影响玩家可见结果，也不改变“解析结果必须属于合法行动”的既有校验。

### 3.2 叙事

- 输入为已提交意图、骰点结果和固定叙事要点；不传入私密记忆、其他 NPC 知识或玩家假设。
- 固定叙事要点来自 `case_content` 对应行动的结局文本，作为不可新增事实的边界。
- 要求输出 2—4 句中文纯文本，不新增人物、线索、地点、数值、判定结果或玩家决定。
- 去掉代码块围栏、首尾引号并压缩空白；空文本、超长文本或残留 JSON 视为失败。
- 失败抛 `SimulationError`，由现有 `_narrate_or_pending` 转为 202 待重试；不自动改写为本地文风。

## 4. 组件

- 新增 `app/provider_config.py`：纯函数读取、校验和选择 Provider，不打印密钥。
- 新增 `app/llm_model.py`：`ProviderModel` 实现 `parse_action`／`narrate`，HTTP 使用现有 `httpx`。
- `app/main.py`：无显式注入时按 `.env` 构建 `ProviderModel(fallback=SimulatedModel())`；`/api/health` 只返回 `model`、`provider`、`model_name`。
- `app/model.py` 与 `GameService` 契约不变。

## 5. 失败与安全

- 所有 HTTP 调用串行；超时、重试有界，不并发抢占 Provider。
- 错误日志只记录状态码、耗时、Provider 名与脱敏原因，不记录密钥、完整请求头或私密提示。
- 在线解析结果仍走既有候选、权限和事务校验，模型不能直接提交行动或改变世界状态。
- 无 `.env`、Provider 不可用或返回非法内容时游戏仍可玩；叙事待重试期间历史可读。
- 自动测试使用 `httpx.MockTransport`，不产生真实网络请求；真实连通性只做人工冒烟。

## 6. 测试与验收

1. 配置读取、环境变量优先、缺省回退与非法配置报错。
2. 合法解析只采用程序目录字段；未知行动、非法 JSON、HTTP 失败回退本地。
3. 叙事清理围栏与引号；失败抛 `SimulationError` 且不泄露密钥。
4. 健康接口只暴露 Provider 与模型名。
5. 既有 109 项测试保持通过，不接网络的测试全程离线。
6. 真实 DashScope 冒烟：解析一条合法行动并生成一段叙事。

## 7. 明确不做

- 不接入流式输出、多 Provider 并发、自动计费统计或复杂路由。
- 不让模型决定事实、骰点、权限、认知、纠正或结局。
- 不写入真实存档做自动验收，不自动执行 Git 写操作。

## 8. 真实联调结果

- 临时库 `%TEMP%\localhero-phase7-browser-20261105-e7a1c3.db`，服务 `127.0.0.1:8765`，真实浏览器完成接委托、询问、安抚、前往新栖公寓、查看住处五步。
- 健康接口返回 `provider=dashscope`、`model_name=qwen3.7-plus`；已存叙事与 `SimulatedModel` 固定文本不同，确认在线叙事实际生效。
- 两次读取同一存档摘要一致；审计 5 条均为 `complete`，候选排除、权限、声明、骰点、版本与认知来源完整；回放校验 `matched`；控制台无脚本错误。
- 联调修复两项前端问题：顶部模型状态改为读取 `/api/health` 动态显示；历史时间线不再重复渲染同一条叙事。
- 叙事扩写优化：提示词把固定要点定义为“不可照抄的事实边界”，允许补充环境光线、声音、气味、温度、材质、体感与动作节奏等不改事实的感官细节，并补充中文判定结果与行动倾向。DashScope 真实冒烟两例的 6-gram 重合度分别为 0.04 与 0.00，叙事不再复述固定要点。

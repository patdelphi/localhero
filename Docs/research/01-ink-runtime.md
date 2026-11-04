# Ink 源码研究：运行时状态、保存恢复与外部函数

## 1. 对象与证据

- 仓库：https://github.com/inkle/ink
- 固定 commit：`35c63e52f1d36060930dc7ed3cfba38ea224b528`
- 提交说明：`Version 1.2.1`
- 提交时间：2026-05-05T12:19:29+01:00
- 许可证：MIT，见本地 `LICENSE.txt`
- 检索日期：2026-11-04
- 本地快照：`research/upstream/ink/`
- 证据范围：Ink 的 C# 运行时，重点是 `Story`、`StoryState`、`StatePatch`、`VariablesState` 与 `Flow`。

以下源码链接均固定到上述 commit；行号用于定位本次实际检查的范围。

## 2. 核心问题

1. Story 推进时，运行时状态由谁持有。
2. JSON 保存和恢复包含哪些状态。
3. StatePatch 是否可以视为事件溯源。
4. 外部函数是否可能被前瞻执行，从而提前或重复产生副作用。

## 3. 核心流程

### 3.1 故事推进

```text
Continue / ContinueAsync
    → ContinueInternal
        → 运行时逐步求值并生成输出
        → 遇到选择、流程边界或外部函数时按运行时规则处理
    → 当前输出、选择、变量与调用栈仍由 StoryState 统一管理
```

关键入口：

- [`Story.Continue()`／`ContinueAsync()`／`ContinueInternal()`](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/Story.cs#L377-L526)
- [`Story` 流程控制与外部函数入口](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/Story.cs#L1137-L1183)
- [`Story` 外部函数执行与 `lookaheadSafe`](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/Story.cs#L1943-L2062)

**源码事实：** 故事推进不是单纯返回一段文本；运行时同时维护流程、输出、选择、变量和求值状态。

**项目判断：** 若未来使用 Ink，它应位于“关键场景内容运行时”层，而不是直接拥有案件事实提交权。

### 3.2 状态保存与恢复

`StoryState` 提供 JSON 保存接口，并通过状态复制、对象构造与 JSON 恢复协作完成快照。

保存内容中可明确定位到：

- 当前 flows 与流程状态；
- 调用栈；
- 输出流；
- 当前选择；
- 变量；
- `visitCounts`；
- `turnIndices` 与当前 `turnIdx`；
- `storySeed`、`previousRandom` 等随机状态；
- 保存格式版本。

关键索引：

- [`StoryState` JSON 保存接口](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/StoryState.cs#L10-L60)
- [`StoryState` 状态复制与补丁协作](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/StoryState.cs#L463-L569)
- [`StoryState` 写入计数、回合、随机状态与保存版本](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/StoryState.cs#L681-L700)
- [`StoryState` 恢复 flows、调用栈、输出流、选择、变量与随机状态](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/StoryState.cs#L704-L785)
- [`Flow` 的流程与当前选择序列化](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/Flow.cs)
- [`Story` 状态快照和后台保存入口](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/Story.cs#L788-L865)

**研究判断：** Ink 的快照适合“恢复故事运行时后继续走”，其设计目标不是记录每一次世界事实为何、由谁、依据哪条规则被提交。

### 3.3 StatePatch 的实际范围

[`StatePatch`](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/StatePatch.cs#L5-L65) 包含：

- globals；
- changedVariables；
- visitCounts；
- turnIndices。

[`VariablesState` 的全局变量写入](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/VariablesState.cs#L355-L379) 会在存在补丁时优先写入补丁。

**源码事实：** StatePatch 表达的是部分变量与计数的增量变化。

**研究判断：** 它更接近后台保存和增量状态合并机制，而不是完整事件日志。它没有在本批证据中呈现出项目所需的事件序号、行动幂等键、审核记录、内容版本、分支父指针或事实因果关系。因此不能把 StatePatch 直接命名为事件溯源。

### 3.4 外部函数与前瞻副作用

`Story` 的外部函数执行路径区分 `lookaheadSafe`。上游源码注释明确提示：前瞻求值可能使外部函数早于正式到达时被调用，甚至重复调用；只有无副作用或可安全前瞻的函数才应标记为安全。

关键证据：

- [`Story` 外部函数执行和 `lookaheadSafe`](https://github.com/inkle/ink/blob/35c63e52f1d36060930dc7ed3cfba38ea224b528/ink-engine-runtime/Story.cs#L1943-L2062)

**项目判断：** 这与本项目“行动、请求幂等、事件记录、事实提交与叙事重试分离”的原则直接相关。任何可能扣费、推进时钟、写数据库或生成事件的外部函数，都不能仅依赖故事引擎的调用次数保证业务正确性。

## 4. 可借鉴清单

1. **独立的故事运行状态。** 将场景内容指针、当前选择、变量和随机状态作为可恢复单元。
2. **显式保存格式版本。** 项目存档与快照应带 schema 版本和内容版本，避免只保存一串文本。
3. **随机状态纳入恢复。** 若要精确续跑，不能只保存骰点结果而丢失后续随机序列状态。
4. **外部效果安全分级。** 可借鉴 `lookaheadSafe` 的思路，将只读查询与有副作用命令明确区分。
5. **适合人工精写场景。** Ink 可作为未来关键对话或固定场景的作者化表达候选，而非全局世界引擎。

## 5. 不采用或不能直接等同的机制

1. 不把 Ink JSON 快照当作完整事件溯源。
2. 不把 StatePatch 当作案件审核、分支历史或事实因果记录。
3. 不允许 Ink 外部函数直接写项目数据库；必须经过程序协调器、显式事务与幂等控制。
4. 不让故事输出文本反向成为案件真相。
5. 当前不引入 Ink 依赖；只有出现足量人工精写关键场景需求时再评估。

## 6. 对架构 2.0 的候选启示

本批只记录候选启示，不直接修订架构：

- 在内容运行时接口中区分“只读求值”“可前瞻函数”“事实提交命令”。
- 快照除世界状态外，还应保存内容运行时指针及随机状态；事件日志则保存造成状态变化的历史。
- 精确回放与重新推演必须分别定义：前者重放既有结果，后者允许重新求值，不能混用 Ink 的“恢复后继续”概念。

## 7. 证据限制

- 未逐行研究 Ink 编译器和 inklecate，也未覆盖所有序列化兼容测试。
- 未验证不同 Ink 版本间的存档迁移。
- 关于 StatePatch 用途的判断限于本批读取的实现与注释，不声称覆盖上游所有使用方式。
- 是否实际嵌入 Ink 不在本批决策范围内。

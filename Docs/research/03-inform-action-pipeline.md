# Inform 7 源码研究：世界模型与行动处理管线

## 1. 对象与证据

- 仓库：https://github.com/ganelson/inform
- 固定 commit：`5c7ba42b74db69b93b1290453c65189fa60cfc67`
- 页面版本：`10.2.0-beta+6Y13 'Krypton' (24 June 2026)`
- 提交时间：2026-06-24T16:52:21Z
- 提交说明：`Tidying after PR#213`
- 许可证：Artistic License 2.0，见本地 `LICENSE`
- 检索日期：2026-11-04
- 本地快照：`research/upstream/inform/inform-master/`
- 获取方式：Git TLS 克隆失败后改用 Codeload ZIP，并通过 GitHub API 固定 master commit；本地目录不是 Git 工作树。
- 证据范围：Standard Rules 的规则簿、行动定义，以及 WorldModelKit 的行动执行和对象关系。

## 2. 核心问题

1. 世界实体、关系和属性如何为行动提供状态基础。
2. Before、Instead、Check、Carry Out、After、Report 如何分层。
3. 行动失败在哪里停止，真正世界变化在哪里发生。
4. Accessibility／Visibility 能为行动权限和可见信息提供什么参考。

## 3. 核心流程

### 3.1 六阶段行动管线

Standard Rules 中的 taking 示例给出以下顺序：

```text
before
    → instead
    → check taking
    → carry out taking
    → after
    → report taking
```

关键索引：

- [action-processing 等规则簿](https://github.com/ganelson/inform/blob/5c7ba42b74db69b93b1290453c65189fa60cfc67/inform7/Internal/Extensions/Graham%20Nelson/Standard%20Rules.i7xd/Source/Sections/Variables%20and%20Rulebooks.w#L309-L340)
- [Accessibility 与 Visibility](https://github.com/ganelson/inform/blob/5c7ba42b74db69b93b1290453c65189fa60cfc67/inform7/Internal/Extensions/Graham%20Nelson/Standard%20Rules.i7xd/Source/Sections/Variables%20and%20Rulebooks.w#L342-L357)
- [六个经典行动阶段及 taking 示例](https://github.com/ganelson/inform/blob/5c7ba42b74db69b93b1290453c65189fa60cfc67/inform7/Internal/Extensions/Graham%20Nelson/Standard%20Rules.i7xd/Source/Sections/Variables%20and%20Rulebooks.w#L368-L392)
- [`BeginAction`](https://github.com/ganelson/inform/blob/5c7ba42b74db69b93b1290453c65189fa60cfc67/inform7/Internal/Extensions/Graham%20Nelson/Standard%20Rules.i7xd/Materials/Inter/WorldModelKit/Sections/Actions.i6t#L308-L333)
- [`ActionPrimitive` 执行规则簿并处理行动结果](https://github.com/ganelson/inform/blob/5c7ba42b74db69b93b1290453c65189fa60cfc67/inform7/Internal/Extensions/Graham%20Nelson/Standard%20Rules.i7xd/Materials/Inter/WorldModelKit/Sections/Actions.i6t#L354-L412)

**源码事实：** 行动不是“解析命令后直接打印结果”，而是由多个规则簿依次决定能否继续、如何改变世界及如何报告。

### 3.2 taking：校验、事实变化和报告分离

`taking` 的 Standard Rules 明确展示：

- Check 阶段处理不能拿自己、他人、部件、固定物、风景物、已持有物和超出携带能力等失败条件。
- Carry Out 的核心世界变化是 `now the actor carries the noun`，并设置 handled 状态。
- Report 阶段输出“Taken.”或旁观者可见的报告。

关键索引：

- [taking 的 Check 规则](https://github.com/ganelson/inform/blob/5c7ba42b74db69b93b1290453c65189fa60cfc67/inform7/Internal/Extensions/Graham%20Nelson/Standard%20Rules.i7xd/Source/Sections/Actions.w#L80-L188)
- [同一范围内的 Carry Out：`now the actor carries the noun`](https://github.com/ganelson/inform/blob/5c7ba42b74db69b93b1290453c65189fa60cfc67/inform7/Internal/Extensions/Graham%20Nelson/Standard%20Rules.i7xd/Source/Sections/Actions.w#L176-L178)
- [WorldModelKit 的携带关系](https://github.com/ganelson/inform/blob/5c7ba42b74db69b93b1290453c65189fa60cfc67/inform7/Internal/Extensions/Graham%20Nelson/Standard%20Rules.i7xd/Materials/Inter/WorldModelKit/Sections/WorldModel.i6t#L282-L311)
- [WorldModelKit 的对象移动](https://github.com/ganelson/inform/blob/5c7ba42b74db69b93b1290453c65189fa60cfc67/inform7/Internal/Extensions/Graham%20Nelson/Standard%20Rules.i7xd/Materials/Inter/WorldModelKit/Sections/WorldModel.i6t#L394-L449)

**研究判断：** Check／Carry Out／Report 是本项目最值得直接吸收的概念分层：校验失败不应产生事实；事实提交成功后才生成报告；报告重试不应重复执行 Carry Out。

### 3.3 Before／Instead／After 的角色

根据六阶段管线和 taking 的通用实现，可作如下区分：

- **Before**：在通用校验与执行前插入场景或对象相关反应。
- **Instead**：以特殊处理替代通常行动流程。
- **Check**：判断行动在当前世界状态下是否合法。
- **Carry Out**：实施通用世界变化。
- **After**：在事实已发生后插入后续反应，并可影响通常报告。
- **Report**：描述已处理行动的结果。

**证据边界：** 上述是本次源码追踪形成的设计层概括，不是对 Inform 所有规则排序、停止／继续规则和特殊例外的完整规范复述。

### 3.4 Accessibility 与 Visibility

Standard Rules 将 Accessibility、Visibility 独立为规则簿，说明“能否行动”与“能否看见／触及”并非全部混在文本生成中。

**项目判断：** 可将其拆成两个明确视图：

1. 行动作用域：当前人物可感知、可触及、可合法尝试的对象。
2. 信息可见性：不同人物或玩家能看到哪些事实、传闻和叙事细节。

但本项目还需额外处理人物认知错误、秘密和传闻，不能只用物理可见性代替知识模型。

## 4. 可借鉴清单

1. **通用行动模板。** 每类行动分别定义前置例外、校验、提交、后续反应和报告。
2. **事实变化集中于 Carry Out。** 项目可要求事实提交只在程序协调器的提交阶段发生。
3. **报告只读已提交结果。** 叙事失败可以重试，不重新掷骰、扣费或推进时钟。
4. **场景例外与通用规则分离。** Before／Instead／After 适合表达特定地点、人物和物品的特殊反应。
5. **可见性与作用域显式化。** 行动候选和 NPC 知识视图均应先过滤再交给模型。
6. **关系作为世界状态。** 携带、包含、位置等关系支持规则判断，而不是靠文字描述推断。

## 5. 不采用或不能直接等同的机制

1. 不把 Inform 规则执行直接等同于 SQLite 事务；项目仍须显式事务保证原子性。
2. 不引入整套自然语言解析器、编译器或 Inter 工具链来解决当前问题。
3. 不让 Before／Instead 规则绕过 A 级权限：场景事实可程序校验后提交，案件事实须独立审核，全球正典须人工批准。
4. 不把物理 Visibility 当成完整人物认知、传闻与秘密模型。
5. 不因规则簿灵活就把所有逻辑写成无约束规则脚本；高频权威状态仍应有明确 schema 和事件记录。

## 6. 对架构 2.0 的候选启示

建议后续评审以下行动骨架，而不是立即修改代码：

```text
行动声明
→ 前置场景例外（Before）
→ 特殊替代流程（Instead，可选）
→ 通用校验（Check）
→ 判定与费用计算（尚未提交）
→ 单事务事实提交（Carry Out + 事件 + 幂等）
→ 已提交事实的后续反应（After）
→ 可独立重试的叙事报告（Report）
```

其中“判定与费用计算”放在事务前只表示计算，不表示提前扣费；实际写入仍与事实、事件在同一事务完成。

## 7. 证据限制

- 本批不是 Inform 编译器、Inter 代码生成、自然语言解析或完整世界模型的全面审计。
- 规则簿的实际完整排序还受更多规则与特例影响，本报告只追踪与项目行动管线有关的调用链。
- 未研究 Inform 的完整保存、撤销和回放实现，不能据此判断其是否满足本项目多分支需求。
- Inform 采用 beta 标识的固定 master 快照，结论不自动适用于其他版本。

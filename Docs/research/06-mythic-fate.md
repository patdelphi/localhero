# Mythic GME 与 Fate：动态场景提示、事实权限与叙事代价

## 1. 对象与证据

### 1.1 Mythic Game Master Emulator Second Edition

- 作者／出版方：Tana Pigeon／Word Mill Games。
- 版本：Second Edition；官方产品页未标注本批可核实的发布日期。
- 官方主页：https://wordmillgames.com/
- 官方产品页：https://wordmillgames.itch.io/mythic-game-master-emulator-second-edition
- 公开范围：付费专有规则书的官方公开介绍，不是开放 SRD；本批未购买或引用完整规则书，也未使用非官方转载 PDF。
- 补充公开材料：https://jasonholtdigital.itch.io/mythic-gme-digital ，其自称为官方 2e  companion app，只用于核对公开展示的功能名称，不等同于核心规则书。
- 检索日期：2026-11-04。

官方公开介绍确认的核心概念包括：Yes/No Question、Random Event、Meaning Table、跟踪目标与人物的 Lists、Scene Structure、Chaos Factor，以及所有结果均受 ongoing Context 中的预期和解释引导。2e 还公开说明具有 Fate Chart、无需图表的 Fate Check 和更动态的 List 管理。

**关键限制：** 公开页面没有给出完整的场景检查阈值、Interrupt Scene 详细定义、Chaos Factor 精确调整规则、Threads／NPC List 增删和选中算法。本报告不会用记忆或非官方教程补齐这些内容。

### 1.2 Fate Core 与 Fate Condensed

- 官方 SRD：https://fate-srd.com/
- Fate Core 章节：
  - https://fate-srd.com/fate-core/aspects-fate-points
  - https://fate-srd.com/fate-core/invoking-compelling-aspects
  - https://fate-srd.com/fate-core/fate-points/
- Fate Condensed 章节：https://fate-srd.com/fate-condensed/aspects-and-fate-points
- 许可证：Creative Commons Attribution 3.0 Unported；官方许可说明：https://fate-srd.com/official-licensing-fate/cc
- 版本：Fate Core 与 Fate Condensed 官方在线 SRD；检索日期为 2026-11-04。

## 2. Mythic GME：公开证据支持的抽象职责

Mythic 的官方介绍把动态主持拆成若干互相配合的机制，而不是一个随机表包办全部工作：

1. **问题与答案**：用 Yes/No 机制处理不确定问题；2e 提供 Fate Chart 和 Fate Check 两种公开命名的方式。
2. **随机事件与意义提示**：Random Event 添加意外，Meaning Table 提供需要解释的提示。
3. **目标与人物列表**：Lists 跟踪重要 goals 和 characters，并在需要时供随机选择。
4. **场景结构**：Scene Structure 为冒险提供形式和顺序。
5. **Chaos Factor**：改变冒险节奏。
6. **Context 约束**：预期与解释必须基于持续发展的上下文，以维持连贯性并允许合理反转。

这些证据足以支持“职责分层”的研究结论，但不足以还原完整可执行算法。尤其是本批计划关注的场景预期、Interrupt Scene、Threads、NPC List 和 Chaos Factor，只能在机制表中标明公开职责及未知边界。

## 3. Fate：Aspect 同时连接事实、权限与机械效果

### 3.1 Aspects Are Always True

Fate Condensed 明确说明 Aspect 即使未被 Invoke 或 Compel 也持续为真，可授予或撤销故事中的行动权限。例如被液压机压住的怪物不能随意移动，直到某事移除该状态（Fate Condensed，`Aspects Are Always True`）。

但 Aspect 不能凭一句强势措辞绕过既定故事约束。其表述必须合理，必要时需要改写。Situation Aspect 通常随场景结束或对应状态被改变而消失；Boost 更短暂，不能 Compel 或付费 Invoke，只能免费使用一次。

### 3.2 Invoke 与 Fate Point

Invoke 需要先解释 Aspect 与当前行动的相关性，再花费 Fate Point 或使用免费 Invoke。Fate Core 的常规收益包括当前判定 +2、重掷全部骰、给他人判定 +2，或提高被动阻力；同一次判定不能重复付费 Invoke 同一个 Aspect，但可使用不同 Aspect 或与免费 Invoke 叠加（Fate Core，`Invoking Aspects`）。

Fate Point 还可用于声明故事细节或激活特定 Stunt。声明细节需要符合范围并可被 GM 否决，因此“支付资源”本身不等于获得无限改写实权（Fate Core，`Fate Points`）。

### 3.3 Compel 是复杂化，不是单纯禁止

Compel 先说明 Aspect 为何相关，再提出复杂化。被 Compel 者可接受复杂化并获得 Fate Point，或支付 Fate Point 阻止它。Compel 可分为外部事件和人物决定两类，关键都在于产生新的复杂局面（Fate Core，`Compelling Aspects`）。

Fate Condensed 进一步区分：好的 Compel 改变处境、提供新问题，而不是只说“你失败，什么也不能做”。Compel 与 Hostile Invoke 也不同：前者创造叙事变化且可拒绝，后者只产生受限机械效果且不可拒绝（Fate Condensed，`Compels`）。

## 4. 可程序化规则机制表

### 4.1 Mythic GME：仅列公开证据能够支持的抽象

| 机制 | 触发条件 | 输入 | 状态变化 | 输出 | 失败边界 |
|---|---|---|---|---|---|
| Fate Question／Fate Check | 出现需要回答的不确定问题 | 明确问题、当前 Context；其他参数未从公开官方资料核实 | 公开资料不足以确定完整状态变化 | Yes/No 类答案；2e 公开确认有图表与无图表两种方式 | 不伪造概率档、骰式或阈值；答案仍需结合 Context |
| Random Event | 公开介绍确认其用于添加意外；精确触发未核实 | 当前场景与 Context；触发表未核实 | 未核实 | 意外事件提示 | 不把所有意外直接提交为世界事实 |
| Meaning Table | 需要重要细节或开放提示 | 问题、相关表、当前 Context | 表本身不必然改变世界 | 供解释的意义提示 | 提示不是完整答案；不得脱离上下文任意组合 |
| Threads／Characters Lists | 冒险中需要跟踪重要目标与人物 | 目标、人物、当前列表 | 官方确认 2e 列表管理更动态；具体增删规则未核实 | 需要时供随机选择的条目 | 不伪造权重、增删时机或选中算法 |
| Scene Structure／场景预期 | 冒险需要形成场景顺序；详细检查条件未公开 | 当前场景预期与 Context | 未核实 | 场景形式与顺序的引导 | Interrupt Scene 的详细定义、奇偶或阈值算法均未由本批官方证据确认 |
| Chaos Factor | 随冒险节奏变化；精确调整时机未公开 | 当前 Chaos Factor 与场景状态 | 公开介绍只确认其改变节奏，具体增减未核实 | 对冒险节奏的影响 | 不填写未核实数值，不把它当作通用“随机度”参数 |
| Context 解释 | 每次使用问题、事件、列表或意义提示 | 已确立事实、当前预期、人物知识 | 将提示解释为与当前故事相容的候选结果 | 连贯结果或合理反转 | 无 Context 的随机结果不能直接成为权威事实 |

### 4.2 Fate：事实、机械效果与叙事复杂化

| 机制 | 触发条件 | 输入 | 状态变化 | 输出 | 失败边界 |
|---|---|---|---|---|---|
| Aspect 持续为真 | Aspect 所描述的事实仍然有效 | Aspect 文本、附着对象、作用域、当前情境 | 不耗资源也持续提供或撤销叙事权限 | 可行动性、难度或状态约束 | 不合理措辞需修正；不能用一句话推翻既有约束 |
| Invoke | 判定前后能解释 Aspect 与行动相关，且有 Fate Point 或免费 Invoke | Aspect、相关性、判定、资源 | 消耗资源并获得 +2、重掷或其他授权收益 | 修正后的判定或被动阻力 | 同一判定不能重复付费 Invoke 同一 Aspect；相关性须获认可 |
| Free Invoke | Create an Advantage、Consequence 等规则赋予免费使用次数 | Aspect、免费次数、来源 | 使用次数减少，不支付 Fate Point | 与常规 Invoke 类似的收益 | 免费次数必须有来源；Boost 使用后消失 |
| Declare Story Detail | 玩家希望加入重要或不太可能的细节 | Aspect、细节、Fate Point、既有故事范围 | 支付资源；经认可后提交细节 | 新故事细节 | GM 可否决或要求修改；支付资源不等于自动通过 |
| Event Compel | 外部力量结合 Aspect 产生不利复杂化 | Aspect、情境、复杂化提案、目标资源 | 接受则复杂化成为故事变化并获得 Fate Point；拒绝则支付 Fate Point | 新事件、关系或处境 | 必须真正复杂化；不能越过世界控制权限 |
| Decision Compel | 人物缺陷或竞争价值促使其作出会出问题的决定 | Aspect、人物动机、决定与后果 | 接受则提交决定及复杂化并获得 Fate Point；拒绝则支付 Fate Point | 人物选择与后续后果 | 不能强迫玩家接受不符合人物的决定；无复杂化则无 Compel |
| Hostile Invoke | 使用对方 Aspect 对其产生当前机械优势 | 对方 Aspect、相关性、Fate Point | 当前判定获得 +2 或重掷；对方获得延迟可用的 Fate Point | 受限机械效果 | 与 Compel 不同，不创造广泛叙事变化，也不给目标拒绝权 |
| Aspect 移除 | 对应状态已改变，或成功执行合理移除行动 | Aspect、移除方法、可能的 Overcome／Defend | 删除或替换 Aspect，恢复或改变权限 | 新情境状态 | 没有叙事阻碍时不必强行掷骰；有阻碍时才按行动处理 |

## 5. 可借鉴清单

1. **随机提示与事实提交分离。** Mythic 的 Context 原则支持先结合现状解释，再决定是否能成为事实。
2. **目标与人物使用显式列表。** 线程和 NPC 应有稳定 ID、状态与来源，随机选择只作用于当前合法候选集。
3. **场景预期可被检验而非被剧本锁死。** 可保留抽象设计方向，但在取得正式规则证据前不实现 Mythic 的具体算法。
4. **事实可带权限效果。** Fate 的“始终为真”提示项目：已提交事实不只用于叙事，还应约束行动合法性。
5. **资源与效果分离。** Invoke 先验证相关性和资源，再应用明确机械效果；叙事文本不直接修改数值。
6. **复杂化需要可审计提案。** Compel 可分为事件与决定两类，接受、拒绝、支付和结果均应记录。
7. **复杂化不等于禁止行动。** 优先产生新处境、关系或代价，而非简单粗暴地取消玩家选择。

## 6. 不采用或不可直接等同的机制

1. 不在未获得正式公开规则证据的情况下实现 Mythic 2e 的精确场景阈值、Chaos 调整或 List 算法。
2. 不把 Mythic 的随机提示直接视为世界事实，也不让 Chaos Factor 成为无约束的 AI 创造性滑块。
3. 不用自然语言 Aspect 单独承担权威事实；仍需结构化状态、作用域、来源与审核级别。
4. 不允许 Fate Point、Invoke 或 Compel 绕过本项目 A 级权限：场景事实、案件事实和全球正典仍走不同提交路径。
5. 不把 Compel 当成导演随意惩罚玩家的入口；必须有相关事实、明确复杂化和可记录的接受／拒绝结果。
6. 不把 Hostile Invoke 与 Compel 合并为一个“负面事件”接口，两者机械范围和拒绝权不同。
7. 不照搬完整 Fate 骰制、技能、Stunt 或经济系统，本批只研究事实与规则效果的连接方式。

## 7. 对架构 2.0 的候选启示

### 7.1 场景与列表的保守实现方向

可先使用项目自有、可解释的列表与场景规则，而非声称复刻 Mythic：

```text
稳定 ID 的线程／NPC 列表
→ 根据分支事实过滤合法候选
→ 可复现随机选择
→ 结合场景预期形成候选变化
→ 连续性与权限审核
→ 提交并记录随机种子、候选集、表版本和审核结果
```

### 7.2 类 Aspect 事实需要显式结构

候选字段包括 `fact_id`、`scope`、`status`、`source_event_id`、`permissions`、`restrictions`、`mechanical_effects`、`review_level` 和 `expires_when`。自然语言描述只负责表达，不作为唯一规则来源。

Compel 类机制则宜采用独立提案状态：`proposed → accepted／rejected／withdrawn → committed`。接受后的复杂化仍须按事实等级审核，拒绝时资源扣除与叙事撤回必须在同一事务中保持一致。

## 8. 证据限制

- Mythic GME 2e 是付费专有规则书。本批只使用官方公开介绍和官方 companion app 的公开功能页，不能据此声称完成完整规则级或算法级研究。
- Mythic 的 Interrupt Scene、Chaos Factor 数值变化、Threads／NPC List 具体管理规则均未获得足够官方公开证据；相关表格刻意保留“未核实”。
- Fate 部分使用官方 Core 与 Condensed SRD，二者个别流程表述和资源细节可能不同；项目借鉴时应明确选择规则来源，不应混写为同一套原生规则。
- 本批未研究 Mythic 或 Fate 的任何软件内部实现，也未验证第三方应用与完整规则书的一致性。
- 所有项目映射均为候选建议，需在全部批次完成后统一评审。

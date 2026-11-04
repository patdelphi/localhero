# PbtA 与 Forged in the Dark：分档后果、风险位置与世界时钟

## 1. 对象与证据

### 1.1 PbtA：以 Apocalypse World 2e 为具体样本

- 对象：Powered by the Apocalypse 设计框架；本报告不把它当作所有游戏完全统一的骰制。
- 规则证据：*Apocalypse World 2nd Edition Basic Refbook*，42 页官方免费 PDF。
- 官方入口：https://apocalypse-world.com/
- PDF：http://apocalypse-world.com/ApocalypseWorldBasicRefbook2ndEd.pdf
- 本地快照：`research/upstream/public-docs/ApocalypseWorldBasicRefbook2ndEd.pdf`
- 公开范围：官方免费下载；本批未确认其采用开放内容许可证，因此仅作机制研究和必要引用。
- 检索日期：2026-11-04。
- 访问核查：2026-11-04 HTTPS 入口因证书主机名不匹配无法读取；HTTP 入口（http://apocalypse-world.com/）及上述官方 Basic Refbook PDF 可读取。该结果只说明入口访问状态，不表示规则内容失效。
- 关键页：PDF 物理页 27（Basic Moves）、37（MC Agenda、Always Say、Principles、Moves）。

### 1.2 Forged in the Dark：以 Blades in the Dark 官方公开规则为样本

- 官方规则入口：https://bladesinthedark.com/core-system
- 其他章节：`actions-attributes`、`action-roll`、`progress-clocks/`、`downtime-activities`、`faction-game`。
- 版本：官方在线公开规则，页面未提供本批可固定的独立版本号；检索日期为 2026-11-04。
- 公开范围：官方网页公开阅读；本批不据此推断源代码或完整书籍的全部内容。

## 2. 核心机制

### 2.1 PbtA：由虚构触发 Move，而不是先选骰子

Apocalypse World 的 Basic Move 把“人物做了什么”放在判定之前。以 `DO SOMETHING UNDER FIRE` 为例，触发条件是在压力或危险下行动；10+ 达成行动，7—9 则由该 Move 给出较差结果、艰难交易或丑陋选择等具体代价，miss 提醒玩家准备承受恶劣后果（PDF 第 27 页）。

因此，7—9 不是所有 Move 共用一个模糊的“半成功文案”，miss 也不能机械解释为“动作没有发生”。每个 Move 应分别定义触发、结果和主持人后续权限。

MC 章节要求“Play to find out what happens”，并提供 announce future badness、offer opportunity with or without cost、tell consequences and ask 等后果工具（PDF 第 37 页）。这说明主持人并非只在失败时随意惩罚，而是依据既有情境、规则和原则推进世界。

### 2.2 FitD：Position 与 Effect 分离

Blades in the Dark 的 Action Roll 顺序为：明确目标 → 选择 action rating → 确定 Position → 确定 Effect → 加入奖励骰 → 掷骰并判断结果。

- **Position**：行动失败或部分成功时，后果有多严重；公开档位为 controlled、risky、desperate。
- **Effect**：行动成功时能够达成多少，不代替成功概率。
- **结果**：6 为成功；4/5 通常成功但伴随后果；1—3 出现由 Position 决定严重程度的恶劣结果。
- **Devil’s Bargain**：一旦接受，其代价无论骰运都会发生。
- **无风险不掷骰**：没有危险或麻烦时，不应为了形式强行进行 Action Roll。

证据章节：https://bladesinthedark.com/actions-attributes 与 https://bladesinthedark.com/action-roll 。

### 2.3 FitD：时钟反映世界，不替代世界

Progress Clock 用于跟踪需要多次行动克服的障碍或逐步逼近的危险，不必预先绑定唯一解决方法。官方特别强调时钟反映虚构状态，而不是脱离虚构自行决定事件速度。

Clock 可表示危险、竞赛、关联目标、任务、拉锯和派系计划。Downtime 时推进派系时钟，使世界能在玩家直接行动之外继续变化；长期项目则按判定结果填充不同格数。派系 Tier、Hold、Rep 和 -3 至 +3 的 status 为势力行动与关系变化提供状态基础。

证据章节：https://bladesinthedark.com/progress-clocks/ 、https://bladesinthedark.com/downtime-activities 、https://bladesinthedark.com/faction-game 。

## 3. 可程序化规则机制表

下表是对公开规则的程序化抽象，不是规则全文，也不表示本项目已经实现这些结构。

| 机制 | 触发条件 | 输入 | 状态变化 | 输出 | 失败边界 |
|---|---|---|---|---|---|
| PbtA Move | 当前虚构满足具体 Move 的文字触发条件 | 行动声明、相关属性、当前情境、Move 定义 | 按该 Move 的 10+／7—9／miss 结果生成已授权后果 | 分档结果、收益、代价或主持人后续行动 | 不满足触发就不套用；miss 不自动等于动作失败；后果不得越过既有真相与权限 |
| PbtA MC Move | 规则或当前局势要求主持人推进后果 | 已确立事实、NPC 目标、原则、当前威胁 | 新增威胁、机会、代价或选择；是否成为事实需另经项目审核 | 可执行后果或叙事提示 | 不能把“想有戏剧性”当作任意改写正典的理由 |
| FitD Action Roll | 有目标且行动伴随危险或麻烦 | 目标、行动评级、Position、Effect、奖励骰 | 依据结果提交成功程度与后果 | 成功、成功带后果或恶劣结果 | 无危险不掷骰；Position 与 Effect 不得合并为一个难度数 |
| Devil’s Bargain | 玩家明确接受额外骰与既定代价 | 代价定义、额外骰、行动上下文 | 代价必定提交，行动结果另算 | 行动判定与独立代价 | 不能因行动成功而删除代价；接受前必须可理解 |
| Progress Clock | 已确立的进展、倒退、危险逼近或竞赛变化 | Clock ID、当前格数、变化量、事实依据 | 增减或填充格数，必要时完成或联动其他 Clock | 新进度、完成信号、可叙事变化 | 没有事实依据不推进；Clock 完成不能凭空决定解决方式 |
| Faction Clock | Downtime 或势力计划达到推进条件 | 派系目标、资源、当前计划、既有关系 | 在玩家直接行动之外推进势力状态 | 新威胁、机会或世界反应 | 不应每回合无差别推进所有 Clock；需遵守派系能力和已知事实 |
| Long-term Project | Downtime 选择研究、调查、建立信任等项目 | 项目、行动、判定结果、所需 Clock | 按结果增加进度 | 项目进展或完成 | 不能把长期项目当成绕过案件事实审核的入口 |
| Faction Status | 玩家或派系行动改变关系与地位 | Tier、Hold、Rep、status、事件依据 | 更新派系关系或地位 | 可用资源、敌对或合作后果 | 数值变化不能替代具体因果；须保存来源事件 |

## 4. 可借鉴清单

1. **触发优先于判定。** 行动管线先判断当前声明满足哪个规则模板，再决定是否掷骰。
2. **每个行动分别定义分档结果。** 7—9 应返回结构化收益、代价和选项，不依赖叙事者临时猜测机械后果。
3. **风险与效果分开。** 当前项目可分别评估“失败会多糟”和“成功能做到多少”，避免只用一个难度值解释全部情况。
4. **无风险行动直接处理。** 普通对话、查看已知信息和无压力移动不必强行掷骰。
5. **Clock 保存可审计进度。** 每次推进记录来源事件、事实依据和前后格数，支持回放与分支。
6. **世界可在玩家视线外推进。** 派系 Clock 适合表达企业清理、媒体发酵、证人转移等已有计划的持续发展。
7. **部分成功提供选择。** 艰难交易和丑陋选择可转成结构化选项，避免模型只输出含糊的损失描述。

## 5. 不采用或不可直接等同的机制

1. 不把所有 PbtA 游戏概括为同一套 2D6 规则；本项目只吸收已核实样本的设计结构。
2. 不让 miss 自动变成“关键线索永久消失”或“主持人可任意改写真相”。
3. 不把 Position 当成纯数值难度，也不让 Effect 自动创造超出行动能力的事实。
4. 不让 Clock 按现实时间无因推进；必须有计划、事件或明确的世界运行依据。
5. 不把桌面主持人的最终裁量直接交给叙事模型；案件事实仍须独立审核，全球正典仍须人工批准。
6. 不照搬完整派系经济、Tier 或 Downtime 子系统，除非后续设计证明有实际需要。

## 6. 对架构 2.0 的候选启示

建议后续评审以下抽象，而非立即修改代码：

```text
行动声明
→ 匹配规则触发条件
→ 无风险则直接校验／提交
→ 有风险则分别计算 Position 与 Effect
→ 生成分档机械结果和候选后果
→ 权限与连续性校验
→ 单事务提交事实、Clock、费用和事件
→ 只读已提交结果生成叙事
```

Clock 事件至少需要 `clock_id`、`source_event_id`、`reason`、`delta`、`before`、`after` 和分支标识，避免只有最终格数而无法追溯原因。

## 7. 证据限制

- PbtA 部分只深入研究 Apocalypse World 2e 的公开 Basic Refbook，不代表所有 PbtA 作品。
- FitD 部分以 Blades in the Dark 官方在线规则为样本，未固定独立版本号，也未覆盖所有特殊行动、团队升级和完整派系规则。
- 本批研究的是规则结构，不是上游软件实现；网页和 PDF 不能证明任何程序内部算法。
- 所有项目映射均为候选建议，需在全部批次完成后统一评审。

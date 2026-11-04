# Façade、Versu 与 Prom Week：戏剧导演、社会实践与社交历史

## 1. 对象与证据

统一检索日期：2026-11-04。本组均为公开论文、官方网页和作者文章研究，不是源码级研究。

| 对象 | 版本／公开范围 | 许可证或使用边界 | 主要来源与定位 | 本地快照 |
|---|---|---|---|---|
| Façade | 2005 年 AIIDE 论文及 2008 年作者文章；对应 2005 年公开版本的设计 | 论文标注 AAAI 版权；文章仅作公开研究，不推断未公开代码 | Mateas／Stern，*Structuring Content in the Façade Interactive Drama Architecture*，`Architecture and Content Structure`、`Beats, Beat Goals and Beat Mix-ins`、`Global Mix-in Progressions`、`Drama Management`，https://new.aaai.org/Papers/AIIDE/2005/AIIDE05-016.pdf ；Mateas／Stern，*Writing Façade: A Case Study in Procedural Authorship*，§3.1，https://electronicbookreview.com/publications/writing-facade-a-case-study-in-procedural-authorship/ | 官方 PDF 因本机证书过期校验失败而未保存；未关闭证书校验 |
| Versu | Evans／Short，IEEE TCIAIG 6(2)，2014 年 6 月，期刊页 113—130 | 作者公开论文仅供研究；未据此确认开源或开放内容许可证 | *Versu—A Simulationist Storytelling System*，§IV—X、§XIII—XIV，https://www.cs.uky.edu/~sgware/reading/papers/evans2014versu.pdf | `research/upstream/public-docs/evans2014versu.pdf`，18 页逐页提取 |
| Prom Week／Comme il Faut | 2012 正式发布游戏；2013 FDG 设计论文与 2014 CiF 作者论文预印本 | 作者公开论文与官网仅供研究；不据此声称代码或内容开放 | McCoy 等，*Prom Week: Designing past the game/story dilemma*，§2、§3.2—3.4、§4，https://mtreanor.com/publications/promWeek-FDG2013.pdf ；McCoy 等，*Social Story Worlds with Comme il Faut*，§III—IV，https://mtreanor.com/publications/TCIAIG-CiF.pdf | 两份 PDF 均保存在 `research/upstream/public-docs/` 并逐页提取 |

Prom Week 本地版本校验：

- `promWeek-FDG2013.pdf`：8 页，SHA-256 `b5b867b94ae4847648ac2d22657612573b698c260257498ded6d3b809a7686d2`。
- `TCIAIG-CiF.pdf`：12 页作者预印本，SHA-256 `0c4a6fa797407a072078f0c3f517e272add222af4315a4faa3217a17b0420de5`。下文页码指此 PDF 页序，不冒充正式期刊页码。
- 官网玩法与作者写作说明：https://promweek.soe.ucsc.edu/2011/11/12/gameplay-and-social-physics/ ，https://promweek.soe.ucsc.edu/2012/02/09/prom-week-authoring-crafting-procedurally-driven-narratives/ 。

## 2. 三种架构位置

### 2.1 Façade：集中导演与局部响应结合

**已验证公开事实：**

1. 架构由 ABL 反应式规划角色、Drama Manager、自然语言与姿态解释规则、动画引擎构成；最高层叙事序列器负责 Beat 排序（AIIDE 论文，`Architecture and Content Structure`）。
2. 一个 Beat 包含约 10—100 个 joint dialog behavior（jdb）；jdb 是 Grace 与 Trip 之间 1—5 行紧密协调的短对话。任一时刻只有一个 Beat 活跃（同文，`Beats, Beat Goals and Beat Mix-ins`）。
3. Beat Goal 的默认序列通常为 transition-in、若干 body、wait、默认 transition-out。玩家输入经 handler 解释后，可增删、重排后续目标，或插入 Beat Mix-in，再回到默认序列。
4. Global Mix-in 与当前 Beat 并行，围绕婚姻、离婚、治疗、物品或一般反应等话题按层级推进；玩家提及相关话题可推动层级（同文，`Global Mix-in Progressions`）。
5. Drama Manager 从未使用且前置条件满足的 Beat 中，选择符合近期作者张力曲线者；权重与优先级也参与选择。它是粗粒度 Beat 排序器，不替代 Beat 内的局部玩家响应（同文，`Drama Management`）。
6. affinity、hot-button、therapy 等社会游戏以计数或状态表示，但玩家主要通过人物的情绪化表演感知变化，而不是直接操作抽象计数。

**研究判断：** Façade 不是“导演逐步写死剧情”，也不是“NPC 完全自由模拟”。它把全局节奏控制放在 Beat 选择，把即时能动性放在 Beat 内目标重排和并行 Mix-in。

### 2.2 Versu：Practice 限定行动空间，Agent 自主评分

**已验证公开事实：**

1. Social Practice 是角色无关的 reactive joint plan，提供行动 affordance，而不直接控制 Agent。constitutive practice 使行动只有在相应社会实践中才成为可选项（论文 §IV、§VIII）。
2. Praxis 以 exclusion logic 句子集合表示完整世界状态。句子激活 Practice／Agent，Practice 提供 affordance，Agent 评分并执行行动，行动增删句子，随后可用 Practice 集合改变（§VI）。
3. Agent 使用 utility-based reactive action selection：实际试算行动后果，评价未来状态，再撤销试算。作者明确将其称为“广而不深”的短期反应式选择，而不是完整长期规划器（§IX，期刊页 122—123；本地 PDF 第 10—11 页）。
4. 规范违规可产生反应性子 Practice；短寿命响应 Practice 会在更新事件出现后销毁，避免人物继续回应“旧闻”（§IX，期刊页 124；本地 PDF 第 12 页）。
5. 跨 Practice 的核心模型包括 beliefs、emotions、relationships、evaluations。关系状态与自我评价比短暂情绪更持久，并可解锁新的 Practice 或人物目标（§X，期刊页 124—125；本地 PDF 第 12—13 页）。
6. 默认所有 Agent 共享权威世界模型，仅对特定误解保存个人信念；论文明确承认这不能完整表达误解，也不能表达高阶信念和量词信念（§IX.F、§XIV.B）。
7. 确定性模拟与记录玩家确切行动支持 playback（§VIII，期刊页 120；本地 PDF 第 8 页）。作者同时指出大量 desire 调参困难、多 Practice 并发增加调试成本，dominating practice 对重要事件的抑制过粗（§XIV）。

**研究判断：** Versu 的关键不是“给 NPC 一个高分目标”，而是用 Practice 限制当前合法行动，再让不同人物对同一行动空间作不同评价。其试算机制只有在严格无副作用时才能安全用于本项目。

### 2.3 Prom Week：社交交换、回应者自主与历史反馈

**已验证公开事实：**

1. 玩家是外部观察者／操纵者，可为角色选择社交交换；游戏展示各角色最愿意发起的靠前选项。CiF 决定可用交换、回应者接受／拒绝及最合适的表演场景（FDG 2013，§2）。
2. 社交状态包括：永久 Trait；公开、双向、二值 Relationship；私密、方向性、数值 Social Network；临时 Status；Social Fact Database（SFDB）；文化知识库 CKB（FDG 2013，§2.2；CiF 预印本第 2—4 页）。
3. Social Exchange 由 intent、前置条件、发起者／回应者 influence rule sets、effects 和 instantiations 构成。intent 是发起者希望产生的社会状态变化，不等同于必然结果（CiF 预印本第 3—4 页）。
4. 发起者评分累加所有适用的交换专属规则与 microtheory 权重；回应者以类似机制独立决定接受或拒绝。FDG 论文给出的回应阈值为总分大于或等于零时接受，否则拒绝（CiF 预印本第 6 页；FDG 2013，§2.2）。
5. effect 表达交换的一条可能结果轨迹，至少通常有接受与拒绝两类；多个 effect 条件同时成立时，选择条件谓词更多、也就是更具体者。instantiation 用带条件的模板对话与动画表现结果（CiF 预印本第 4、7—8 页）。
6. 表演实现后提交社会状态变化并写入 SFDB，再运行 trigger rules 处理跨交换衍生状态。SFDB 同时供后续规则推理、台词引用和由初始状态重建玩家社会世界使用（FDG 2013，§2.2；CiF 预印本第 4、8 页）。
7. microtheory 把朋友、敌人等跨交换共享的社会知识从具体交换规则中抽出，减少重复写作；交换专属规则只保留该行动的特殊考虑（FDG 2013，§3.2；CiF 预印本第 7 页）。
8. 故事层由作者设定初始局面、关卡人物、目标与结局组合。结局主要由已完成目标组合决定，同时用模板引用玩家实际经历的交换；开放解法不等于无作者结构（FDG 2013，§2.1；CiF 预印本第 10 页）。
9. 测试中发现复杂模拟虽可信却难预测，正式版将目标改到界面可见、与明显交换 intent 对应的状态，并提供有限 SIP 资源用于查看或改变回应。作者明确指出其轨迹分析不能证明故事满意度或完整设计目标（FDG 2013，§3.3—3.4、§4）。

**研究判断：** Prom Week 的动态性来自“固定社交规则与内容池＋可变状态＋玩家选择＋回应者判断＋历史反馈”，不是即时自由生成任意剧情。

## 3. 可程序化机制表

| 机制 | 触发条件 | 输入 | 状态变化 | 输出 | 失败或越界边界 |
|---|---|---|---|---|---|
| Façade Beat 选择 | 前一 Beat 结束或需要全局排序 | 未使用 Beat、前置条件、近期张力曲线、权重与优先级 | 激活一个 Beat | 粗粒度剧情单元 | 不得把 Beat 选中视为其中全部事件已发生 |
| Beat Handler／Mix-in | 玩家话语或姿态被解释为特定 discourse act | 当前 Beat、默认目标序列、输入解释 | 增删或重排目标，插入局部响应 | 玩家响应并回到主线序列 | 无法解释的输入需要 deflection／recovery；不能任意改世界 |
| Versu Practice | 世界句子满足激活条件 | 当前 Practice、参与角色、affordance | Practice 只提供合法行动空间 | 可选行动 | 行动不可用时不能因高 utility 强行执行 |
| Versu 行动试算 | Agent 比较候选行动 | 当前状态、候选行动、desire／evaluation | 暂时试算后果，评分后撤销 | 选中的行动 | 试算不得留下事件、关系或数据库副作用；不是长期规划保证 |
| CiF 欲望形成 | 需要列出人物愿意发起的交换 | Trait、关系、私密网络、状态、历史、CKB、规则权重 | 只计算 volition，不直接提交社交变化 | 排序后的交换候选 | 分数高不等于行动已发生或对方接受 |
| CiF 回应判断 | 玩家／发起者选定交换 | intent、回应者规则、当前社会状态 | 确定接受／拒绝，再选择具体 effect | 回应结果 | 回应者有自己的判断，不能把 intent 直接当结果 |
| CiF effect／instantiation | 接受／拒绝及附加条件已确定 | effect 条件、表演条件、模板 | 选中一条具体结果轨迹与表演 | 对话和动画脚本 | 模板只表现已选结果，不应自行创造未提交事实 |
| CiF 历史与触发器 | 交换表演完成并形成状态结果 | 交换上下文、社会标签、状态变化 | 写 SFDB，再运行 trigger rules | 可供后续推理和引用的历史 | 级联规则必须有限、可审计；不能把全部历史默认公开给所有角色 |
| Prom Week 故事目标 | 关卡开始及每次社交状态提交后 | 作者目标、可见状态、交换历史 | 记录完成、进展或反进展 | 目标反馈及结局组合输入 | 目标完成率不能证明叙事质量；隐藏目标状态会降低可理解性 |

## 4. 可借鉴清单

1. **全局导演与局部响应分层。** 可让场景导演只选择候选场景单元，人物行动和玩家输入在单元内改变局部路径。
2. **候选内容必须有前置条件与回退。** Beat、Practice、社交交换都只从当前合法集合中选择；无法响应时使用明确回退，而非伪造结果。
3. **行动意图与结果分开。** 发起者希望改变什么、回应者是否接受、最终提交哪些事实，应是三个独立数据对象。
4. **人物自主先采用短期可解释评分。** 当前项目无需长期规划器；确定性 utility 评分更适合本地串行模拟和测试。
5. **共享规则与特殊规则分开。** 可抽取少量跨行动通用规则，特殊行动只写差异，避免每条行动重复整套社会常识。
6. **历史同时服务决策与表达。** 已提交事件可被后续行动规则查询，也可为台词提供准确回忆，但两者都只能读取有权限的事实视图。
7. **长期关系与短期情绪分开。** 关系变化需要显著事件和明确记录，短期状态应带持续期或结束条件。
8. **可理解性属于机制正确性的一部分。** 重要目标、行动可能结果和人物回应理由需要可检查的摘要，不能只追求内部模拟复杂度。
9. **回放依赖确定性输入与内容版本。** Versu 和 Prom Week 的公开资料都支持记录确切行动并重建状态的价值；本项目还应保留随机种子、规则版本和事件 ID。

## 5. 不采用或不可直接等同的机制

1. 不直接复制 Façade 的 ABL、jdb 大规模内容量或专用张力曲线算法；本项目当前只需要抽象导演分层。
2. 不让全局导演绕过行动校验与事实审核，直接指定案件真相或全球正典。
3. 不把 Versu 的共享权威认知模型照搬为所有 NPC 全知；本项目必须保留人物认知、传闻与主持人秘密隔离。
4. 不在候选评分阶段执行真实数据库写入、事件追加或外部副作用。
5. 不引入 Versu 的大规模 desire 调参和复杂并发 Practice 体系，也不采用过粗的全局 dominating practice 一刀切。
6. 不照搬 CiF 的“全部 SFDB 历史公开”设定，不把公开双向关系与私密方向性感受混成一类事实。
7. 不一开始建设 5,000 条社会考虑、大量 microtheory 或近千个场景模板；先验证少量规则能否产生可解释差异。
8. 不把随机模板台词当作事实来源，也不允许叙事层补写未审核的关系、线索或秘密。
9. 不把 Prom Week 的轨迹分支数量当作叙事质量证明，也不把其 SIP 机制视为本项目必需功能。

## 6. 对架构 2.0 的候选启示

### 6.1 候选调度链

```text
场景导演提出合法场景单元
→ Practice／行动模板给出当前 affordance
→ 玩家或 NPC 形成行动意图
→ 回应者与规则独立判定
→ 在隔离状态中试算并比较候选
→ 校验事实权限、连续性与审核级别
→ 单事务提交事件及状态
→ 叙事层读取已提交事实进行表现
→ 有界衍生规则处理后续反应
```

这条链是项目建议，不是任何一个上游系统的原样流程。场景导演只拥有候选排序权；案件事实仍需独立审核，全球正典仍需人工批准。

### 6.2 社交事实的最小分型

候选类型包括：

- `public_relationship`：双方公开承认或社会可见的关系状态；
- `directed_evaluation`：某角色对另一角色的方向性评价，不自动共享；
- `temporary_state`：带开始原因、持续期和结束条件的短期状态；
- `actor_belief`：角色个人认知，可错误，必须与世界真相分离；
- `social_memory`：引用来源事件的记忆条目，带可见范围、社会标签和有效时间窗；
- `character_goal`：稳定目标、进度证据和完成条件，不直接等于剧情结局。

自然语言台词只能读取这些结构化事实及其授权视图，不得自行提升为权威事实。

### 6.3 安全试算与审计

若采用 Versu 式“试算后果再评分”，优先使用纯函数状态副本；若必须借用数据库事务，候选试算只能回滚且禁止追加正式事件。每次最终选择至少记录候选集、适用规则、分值、选中原因、内容版本和提交事件 ID，以便精确回放与重新推演。

## 7. 证据限制

- 本组没有获得 Façade、Versu 或 Prom Week 的固定版本源码，所有内部数据结构与算法描述仅限论文明确公开的内容。
- Façade 官方 AAAI PDF 在本机两次以不同客户端下载均因 TLS 证书信任问题失败，未绕过校验；具体结论来自官方论文网页提取与作者文章，未对本地 PDF 页码和哈希作虚假声明。
- Façade 的完整 Beat 选择公式、优先级细节、自然语言理解准确率和全部恢复策略未由本组还原。
- Versu 论文说明其确定性 playback，但本组未验证具体存档格式、跨版本兼容或完整分支实现。
- CiF 使用的是 12 页作者预印本；正式期刊版为 2014 年 TCIAIG 6(2)，页 97—112。二者排版和部分内容可能不同，本报告页码只对应本地预印本。
- Prom Week 的公开轨迹证明路径变化，不证明每条路径都具有同等叙事质量；作者也明确保留更严格评估为后续工作。
- 所有项目映射均为候选建议，需在第三批结束后统一进入跨系统矩阵和架构 2.1 评审；本轮不修改游戏代码、不接 AI Provider。

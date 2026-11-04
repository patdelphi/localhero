# 《灰区事务所》参考系统研究总索引

## 1. 研究目的与边界

本研究为《动态叙事架构 2.0》提供可追溯的设计依据，不直接修改游戏代码，不接入 AI Provider，也不把第三方系统整体引入项目。

研究坚持三项区分：

- **源码事实**：能够定位到固定版本中的具体文件、符号或代码路径。
- **研究判断**：根据源码事实作出的解释，不等同于上游项目的官方承诺。
- **项目建议**：面向《灰区事务所》的取舍，仍需经过后续设计评审。

第一批研究 Ink、Yarn Spinner、Inform 7；第二批研究 PbtA／Forged in the Dark、GUMSHOE／Ironsworn、Mythic GME／Fate；第三批研究 Façade／Versu／Prom Week 与 Wildermyth／Shadows of Doubt／Dwarf Fortress。三批对象研究、最终跨系统矩阵和架构 2.1 修订建议现已完成；第 8 项总自查与最终复验已完成，详见第 13 节。

## 2. 证据等级与统一模板

### 2.1 证据等级

| 等级 | 含义 | 使用方式 |
|---|---|---|
| A | 固定 commit 的本地源码或许可证 | 可描述具体实现，但必须附文件与行号 |
| B | 官方文档、规则书、论文或开发者公开材料 | 可描述公开设计，不推断未公开实现 |
| C | 基于 A/B 证据的研究判断 | 必须明确写成判断或建议 |

### 2.2 单对象证据模板

1. 对象、仓库、固定 commit、版本性质、许可证、检索日期。
2. 本地源码快照与文档入口。
3. 研究问题及实际追踪的调用链。
4. 核心流程。
5. 关键源码索引。
6. 已验证事实、研究判断、项目建议。
7. 可借鉴与不采用清单。
8. 证据限制与未验证事项。

## 3. 第一批对象与固定版本

统一检索日期：2026-11-04。第三方源码保存在 `research/upstream/`，该目录已加入 `.gitignore`，不进入项目提交。

| 对象 | 官方仓库 | 固定 commit | 版本性质 | 许可证 | 本地快照 |
|---|---|---|---|---|---|
| Ink | https://github.com/inkle/ink | `35c63e52f1d36060930dc7ed3cfba38ea224b528` | 提交说明为 `Version 1.2.1` | MIT | `research/upstream/ink/` |
| Yarn Spinner | https://github.com/YarnSpinnerTool/YarnSpinner | `c5215f86dd5a6761aecbdc9f60f6a6108f91f919` | 固定 master 快照，非本研究认定的稳定发布版 | MIT | `research/upstream/yarn-spinner/` |
| Inform 7 | https://github.com/ganelson/inform | `5c7ba42b74db69b93b1290453c65189fa60cfc67` | master 快照；页面标识 `10.2.0-beta+6Y13 'Krypton'` | Artistic License 2.0 | `research/upstream/inform/inform-master/` |

版本补充：

- Ink 固定提交时间为 2026-05-05T12:19:29+01:00。
- Yarn Spinner 固定提交时间为 2026-10-14T11:31:38+11:00。
- Inform 固定提交时间为 2026-06-24T16:52:21Z，提交说明为 `Tidying after PR#213`。
- Inform 的 Git TLS 克隆失败后，改用 GitHub Codeload ZIP，并通过 GitHub API 核实对应 master commit；本地目录不是 Git 工作树。

## 4. 第一批文档

1. [Ink 运行时状态、保存恢复与外部函数](01-ink-runtime.md)
2. [Yarn Spinner 对话虚拟机与宿主状态边界](02-yarn-spinner-dialogue.md)
3. [Inform 7 世界模型与行动处理管线](03-inform-action-pipeline.md)

## 5. 第一批初步对照矩阵

本表只覆盖第一批源码结论，不替代全部批次完成后的跨系统最终矩阵。

| 评价维度 | Ink | Yarn Spinner | Inform 7 | 对本项目的直接启示 |
|---|---|---|---|---|
| 核心定位 | 作者化互动叙事运行时 | 对话编译产物与虚拟机 | 世界模型、规则簿与行动系统 | 三者解决不同层问题，不能互相替代 |
| 行动／规则管线 | 以故事推进、选择和流程跳转为中心 | 以 Line、Command、Options 交付为中心 | Before／Instead／Check／Carry Out／After／Report 分层明确 | 自研行动管线主要参考 Inform，而非对话引擎 |
| 状态所有权 | StoryState 管理故事运行状态，外部函数连接宿主 | 变量读写经宿主接口，内存库只是可选实现 | 世界模型持有实体、关系与行动状态 | 对话运行状态与权威世界事实必须分离 |
| 保存与恢复 | JSON 覆盖 flows、调用栈、输出流、选择、变量、计数和随机状态 | 所查核心运行时未见完整对话存档协议，主要由宿主负责 | 本批未研究其完整存档格式 | 存档格式应按自身事件溯源需求设计，不能直接照搬 |
| 增量状态 | StatePatch 覆盖部分全局变量与计数 | 未以增量故事状态补丁为核心 | 规则执行不是数据库事务 | StatePatch 不等于事件溯源 |
| 文本与事实 | 输出流可随故事状态保存 | Line 是对话交付单元 | Report 主要负责报告，Carry Out 才改变世界 | 叙事生成失败不得反向重复提交事实 |
| 外部副作用 | 外部函数可能在前瞻中提前或重复执行 | Command 等由宿主处理，宿主需自行保证事务与幂等 | 规则可直接改世界，但不提供本项目数据库事务语义 | 所有外部效果纳入程序协调器、事务和幂等边界 |
| 多分支与回放 | 本批未见满足项目需求的分支事件溯源机制 | 同左 | 同左 | 继续保留自研分支、事件日志、快照和回放设计 |
| 最适合的用途 | 人工精写关键场景与受控分支 | 人物对话协议和选项呈现 | 行动分层、通用规则与场景例外规则 | 组合借鉴机制，不引入完整引擎堆栈 |

## 6. 第一批综合结论

1. **对话引擎不是世界事实权威。** Ink 和 Yarn Spinner 都能推进内容，但本项目的案件真相、人物认知、传闻和 AI 提案仍须由独立世界状态与审核管线管理。
2. **行动事实与叙事报告应分离。** Inform 的 Check／Carry Out／Report 分层与本项目现有事务边界最接近，可转化为“前置例外—校验—提交—后续反应—报告”。
3. **保存状态不等于可追溯历史。** Ink 的 JSON 与 StatePatch 可恢复或合并运行状态，但不能替代事件日志、内容版本、精确回放和重新推演。
4. **宿主副作用必须显式治理。** Ink 的前瞻调用警告与 Yarn 的宿主处理模型都说明，不能把外部函数或 Command 当成天然安全、只执行一次的事务操作。
5. **不在本批决定引入任何依赖。** 当前只吸收机制；是否嵌入 Ink/Yarn 运行时，应在后续有明确内容需求时单独评审。

## 7. 第二批对象与公开资料

统一检索日期：2026-11-04。本批没有源码级结论，只使用官方公开规则书、SRD、官方网页与公开产品说明。

| 对象 | 版本／公开范围 | 许可证或使用边界 | 官方来源 | 本地快照 |
|---|---|---|---|---|
| Apocalypse World（PbtA 样本） | 2e Basic Refbook，官方免费 PDF | 官方公开下载；未据此确认开放内容许可证 | https://apocalypse-world.com/ | `research/upstream/public-docs/ApocalypseWorldBasicRefbook2ndEd.pdf` |
| Blades in the Dark（FitD 样本） | 官方在线公开规则，未固定独立版本号 | 仅作公开规则研究，不推断软件实现 | https://bladesinthedark.com/core-system | 无 |
| GUMSHOE SRD | CC version 3，文件标识 `241209` | CC BY 3.0 | https://pelgranepress.com/2013/10/24/the-gumshoe-system-reference-document/ | `research/upstream/public-docs/GUMSHOESRDCC-3-241209.pdf` |
| Ironsworn | Digital Edition，PDF 标注 Updated June 9, 2019 | 文本 CC BY-NC-SA 4.0 | https://tomkinpress.com/collections/downloads-for-ironsworn | `research/upstream/public-docs/Ironsworn-Digital-Edition.pdf` |
| Mythic GME | Second Edition 官方公开介绍；完整规则书为付费专有资料 | 未使用非官方转载；未核实的算法明确留空 | https://wordmillgames.itch.io/mythic-game-master-emulator-second-edition | 无 |
| Fate Core／Condensed | 官方在线 SRD | CC BY 3.0 | https://fate-srd.com/ | 无 |

## 8. 第二批文档

1. [PbtA 与 Forged in the Dark：分档后果、风险位置与世界时钟](04-pbta-forged-in-the-dark.md)
2. [GUMSHOE 与 Ironsworn：核心线索保障、誓言进度与上下文 Oracle](05-gumshoe-ironsworn.md)
3. [Mythic GME 与 Fate：动态场景提示、事实权限与叙事代价](06-mythic-fate.md)

## 9. 第二批初步机制对照

本表只覆盖第二批公开规则结论，不替代全部批次完成后的最终矩阵。

| 系统 | 核心贡献 | 状态与事实边界 | 失败或越界处理 | 对本项目的候选启示 |
|---|---|---|---|---|
| Apocalypse World | Move 触发与 10+／7—9／miss 分档后果 | 后果来自具体 Move、情境和主持人权限 | miss 不自动等于动作失败，也不能任意改写真相 | 每个行动模板分别定义触发、收益、代价和选项 |
| Blades in the Dark | Position／Effect、Action Roll、Progress／Faction Clock | Clock 反映虚构状态，派系状态支撑世界推进 | 无危险不掷骰；Clock 无事实依据不推进 | 风险与效果分开，Clock 变化记录来源事件 |
| GUMSHOE | 核心线索保障、额外花费、非单线场景网络 | 获得线索与理解真相分离，人物知识独立记录 | 坏骰不能删除必要线索；替代合理方法仍可获得 | 核心线索设置保障和替代路径，花费只买额外优势 |
| Ironsworn | Vow、Milestone、Progress Roll、Oracle | 进度积累与结局判定分离；Oracle 依赖上下文解释 | 普通事件不计里程碑；Oracle 不是完整 GM 模拟器 | 里程碑引用事实证据，随机提示先审核再提交 |
| Mythic GME | 问题、事件、意义表、列表、场景和 Chaos 的职责分层 | 所有结果由 ongoing Context 引导 | 公开证据不足以还原完整算法，不填伪精确规则 | 只借鉴抽象分层，暂不实现其专有具体算法 |
| Fate | Aspect 持续为真、Invoke、Compel、Fate Point | 事实可授予或撤销行动权限；机械与叙事效果分开 | Compel 必须复杂化且可拒绝；资源不能绕过权限 | 结构化事实权限与复杂化提案，保留接受／拒绝记录 |

## 10. 第三批对象与公开资料

统一检索日期：2026-11-04。本批没有固定版本源码级结论；只使用公开论文、官方网页、作者文章、开发者日志、公开演讲页和明确标注的社区文档。网页快照未另存，Prom Week／Versu 等公开 PDF 仅保存在已 Git 忽略的 `research/upstream/public-docs/`。

| 对象 | 版本／公开范围 | 许可证或使用边界 | 主要证据 |
|---|---|---|---|
| Façade | 2005 AIIDE 论文及 2008 作者文章 | AAAI 论文及公开文章仅供研究；未推断代码开放 | 官方论文网页与作者文章；官方 PDF 因本机证书信任失败未保存，未绕过校验 |
| Versu | Evans／Short，IEEE TCIAIG 6(2)，2014 | 作者公开论文仅供研究 | 固定公开 PDF，§IV—X、§XIII—XIV |
| Prom Week／CiF | 2012 游戏、2013 FDG 论文、2014 作者预印本 | 公开论文与官网仅供研究 | 两份固定公开 PDF 与官方玩法／写作说明 |
| Wildermyth | 2021 正式版及 2019—2025 官方写作／模组文档 | 专有商业游戏；不推断代码或内容开放 | 官方 Writer's Guide、Data Format Overview、Story Inputs and Outputs、Event Types、Legacy 与 GDC 2022 简介 |
| Shadows of Doubt | 2018 原型、2023 抢先体验、2024 1.0 及当前官网 | 专有商业游戏；早期设计不自动代表现版 | ColePowered DevBlog #2、#8、#30、#33、#41 与官方游戏页 |
| Dwarf Fortress | Classic 53.16；历史证据跨 v0.40、2018、2019 开发期 | 专有游戏；社区 Wiki 不等同固定源码 | Bay 12 官网与开发日志、2014 Tarn Adams 访谈、明确标注的社区 Legends／XML 文档 |

### 10.1 第三批文档

1. [Façade、Versu 与 Prom Week：戏剧导演、社会实践与社交历史](07-facade-versu-prom-week.md)
2. [Wildermyth、Shadows of Doubt 与 Dwarf Fortress：程序事件、动态调查与世界历史](08-reference-games-history-simulation.md)

### 10.2 第三批初步机制对照

本表只覆盖第三批公开资料结论，不替代后续跨系统最终矩阵。

| 系统 | 核心贡献 | 状态与事实边界 | 失败或越界处理 | 对本项目的候选启示 |
|---|---|---|---|---|
| Façade | Beat 全局排序与 Beat 内局部响应 | Drama Manager 不替代具体行动与玩家响应 | 无法解释的输入需要恢复，不能把 Beat 选中当作结果已发生 | 场景导演与局部行动分层 |
| Versu | Practice 限定 affordance，Agent 短期试算评分 | 默认共享权威模型不等于本项目所需人物认知隔离 | 试算必须无副作用；不可用行动不能靠高分强选 | 合法行动空间与人物评价分开 |
| Prom Week／CiF | 发起者 volition、回应者判断、effect 与 SFDB | intent 不等于结果，历史同时服务规则与表演 | 回应者可拒绝；模板不能创造未提交事实 | 意图、回应、结果提交三段分离 |
| Wildermyth | 情境事件过滤、角色选角、History／Aspect、Legacy | 历史文本不可直接查询，Aspect 才供规则使用；跨局提升显式发生 | 角色不适配则事件不绿灯；不伪造全局导演算法 | 同源写履历与结构状态，跨局版本隔离 |
| Shadows of Doubt | 城市行动、观察记忆、物件持久化与程序调查 | 世界真相、证人记忆和玩家证据板不能等同 | 假阳性、记忆衰减与原型报案失败提示调查链需回退 | 真相、观察、证词、玩家假设分型 |
| Dwarf Fortress | 模拟沉淀历史、反派事件链、目击调查与 Legends | Legends 是查询／导出视图，不是无损日志或逐事件回放 | 失败和死亡也留痕；XML 不完整且现版字段有证据缺口 | 来源事件驱动时间线，历史查看与确定性回放分开 |

## 11. 最终跨系统对照矩阵

1. [跨系统最终对照矩阵：机制复用、冲突与复杂度边界](09-cross-system-final-matrix.md)
2. [动态叙事架构 2.1 参考研究修订建议](../design/2026-11-04-dynamic-narrative-architecture-2.1-research-revisions.md)

矩阵汇总 15 个参考系统的九类统一评价维度；架构 2.1 建议据此形成 A01—A12 十二项修订，保留 2.0 原文及 A 级权限、知识隔离、程序提交和多分支边界。两份文档均不把上游机制描述为本项目已实现功能，也不替代全部证据总自查。

## 12. 证据限制

- 第一批是与项目问题有关的调用链研究，不是三个项目全部源码的逐行审计。
- Yarn Spinner 和 Inform 使用固定 master 快照，不能把结论自动外推到其他版本。
- 第一批未实测 Ink/Yarn 的二进制兼容、跨版本迁移或所有运行平台差异。
- Inform 的编译器、Inter 代码生成和完整世界模型十分庞大，第一批只追踪行动、规则簿及与 taking 相关的世界关系。
- 第二批是公开规则与官方资料研究，不是上游软件源码或内部算法研究；在线网页未固定独立版本号。
- Mythic GME 2e 完整规则书未公开，本批只确认官方公开介绍中的职责分层，场景阈值、Chaos 调整和列表算法均保留证据缺口。
- 第三批没有固定版本源码；Façade 官方 PDF 下载受证书信任失败限制，Shadows of Doubt 早期原型与现版严格分栏，Dwarf Fortress 社区 Wiki 的现版准确性警告予以保留。
- 第 8 项总自查与最终复验已完成，具体结果见第 13 节；以上证据限制继续有效。

## 13. 总自查结果

核查时点：2026-11-04。状态：**第 8 项总自查与最终复验已完成。**

- 固定证据与本地链接：30 个固定源码链接的本地映射最终复验全部通过，其中 29 个行号范围均未越界、1 个为整文件链接；10 份研究 Markdown、架构 2.1 与 Docs/design/todo.md 共 48 个相对链接目标全部存在；AW／GUMSHOE／Ironsworn 关键 PDF 页此前已核对。
- 外部 URL：共核查 46 个去重 URL，36 个通过、5 个部分通过、5 个失败。通过只代表本轮所核内容支持现有表述，不代表来源已成为永久固定版本。

| 文档 | 通过 | 部分 | 失败 |
|---|---:|---:|---:|
| 04 | 7 | 0 | 1 |
| 05 | 1 | 1 | 1 |
| 06 | 9 | 0 | 0 |
| 07 | 6 | 0 | 1 |
| 08 | 13 | 4 | 2 |
| **合计** | **36** | **5** | **5** |

- 具名访问限制：AW HTTPS 证书主机名不匹配，但 HTTP 入口及官方 Basic Refbook PDF 可读取；Ironsworn 集合页部分读取、产品页 TLS 失败；Façade AIIDE PDF TLS／证书信任失败。
- 具名读取范围：Shadows DevBlog #2 受 CAPTCHA 阻挡；Polygon 访谈遭域名级匿名访问封禁；Wildermyth GDC 只核公开简介。上述失败不等于原内容错误，相关原引文不因此被推翻，也不以搜索摘要替代全文。
- 保留证据边界：Mythic 公开介绍不是完整规则；第三批不是固定版本源码研究；CiF 使用作者预印本；Shadows 原型与现版分栏；Dwarf Fortress 社区 Wiki 与历史版本警告、网页未固定等限制继续按各专题报告执行。
- PDF 哈希复核：AW、GUMSHOE、Ironsworn、evans2014versu、promWeek-FDG2013、TCIAIG-CiF 六份本地 PDF 的 SHA-256 最终复算均与文档记录一致。其中以下四个本地文件的实算 SHA-256：

| 本地文件 | 实算 SHA-256 |
|---|---|
| `ApocalypseWorldBasicRefbook2ndEd.pdf` | `d523665f29a9fc6ff6107687221b044f6706361aa3e002f8b924cad554b18df8` |
| `GUMSHOESRDCC-3-241209.pdf` | `430b138ed17054b507b29c7c77e8c51d17874cd000e4176f427749fb014fabc0` |
| `Ironsworn-Digital-Edition.pdf` | `c1cfba6573cbd57ecb1aa02ad925b57e6946468da58f88ae0fd9c7013496e2b9` |
| `evans2014versu.pdf` | `eedff9e6d5adfd464534eeff6acc12893280f7e5d3de5068f82c16913830aa2c` |

Façade AIIDE PDF 仍无本地快照和哈希，保持原有限制。

- 文档修正与格式：Versu 四处期刊页与本地 PDF 页码类型、AW 访问状态、Wildermyth 修订／发布日期元数据、Shadows DevBlog #33／#41 的 itch 当前页面日期均已按证据澄清；机制结论不变。10 份研究 Markdown、架构 2.1、Docs/design/todo.md 及本规格 3 份文档共 15 份文件均为 UTF-8 BOM＋CRLF，无裸 LF／CR。

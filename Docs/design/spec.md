# 第二批规则与动态主持研究实施规格

## 1. 目标与边界

完成 PbtA／Forged in the Dark、GUMSHOE／Ironsworn、Mythic GME／Fate 的公开资料研究，形成可追溯的规则机制表和项目候选启示。

- 不修改 `app/`、测试或游戏功能。
- 不接 Strata 或任何 AI Provider。
- 不自动开始第三批，不形成最终跨系统矩阵或架构 2.1 修订稿。
- 不执行 Git commit、push、merge 或 pull。
- 第三方 PDF 和提取文本只保存在已被 Git 忽略的 `research/upstream/`。

## 2. 已确认证据

1. Apocalypse World 2e Basic Refbook：Basic Moves 的触发、10+／7—9／miss 分档；MC 的“Play to find out what happens”与后果工具。证据为 PDF 第 27、37 页。
2. Blades in the Dark 官方网页：Position／Effect、Action Roll 六步、Progress Clock、Faction Clock 与 Downtime。
3. GUMSHOE SRD CC version 3：核心线索不依赖骰点，合适能力与其他合理方法均可取得；花费购买额外优势；避免硬性单线核心线索顺序。证据为 PDF 第 49、50、92、96 页。
4. Ironsworn 官方数字规则书：Vow、Progress Track、Progress Roll、Ask the Oracle 与 Solo Play。证据为 PDF 第 25、29、109—113、118—119、176、239 页；文本许可证为 CC BY-NC-SA 4.0。
5. Mythic GME 2e 官方产品页：确认 Fate Question、Random Event、Meaning Table、Threads／Characters Lists、Scene Structure、Chaos Factor 及 Context 解释的职责；完整阈值、场景检查和列表更新算法未公开，不得用非官方转述补齐。
6. Fate Core／Condensed 官方 SRD：Aspect 始终为真并可授予或撤销叙事权限；Invoke 消耗 Fate Point 或使用免费 Invoke；Compel 必须造成复杂化而非单纯拒绝行动，接受后获得 Fate Point，拒绝需支付 Fate Point。许可证为 CC BY 3.0。

## 3. 精确交付文件

### 新建

1. `Docs/research/04-pbta-forged-in-the-dark.md`
2. `Docs/research/05-gumshoe-ironsworn.md`
3. `Docs/research/06-mythic-fate.md`

每份统一包含：对象与证据、核心机制、可程序化规则机制表、可借鉴清单、不采用或不可直接等同清单、对架构 2.0 的候选启示、证据限制。

机制表固定列为：机制、触发条件、输入、状态变化、输出、失败边界。项目映射只写候选建议，不写成已实施功能。

### 修改

1. `Docs/research/00-research-index.md`
   - 将研究范围从“仅第一批”改为“第一批已完成、第二批已完成、第三批未开始”。
   - 追加第二批对象、版本／公开范围、许可证、URL、本地快照与三份文档链接。
   - 追加仅限第二批的初步机制对照，不替代最终矩阵。
2. `Docs/design/todo.md`
   - 研究计划标题改为“第一批、第二批完成”。
   - 更新最近状态说明，删除“第二批尚未开始”的旧状态。
   - 第 4 项标为 `[x]`，记录本批开始与完成时间；第 5—8 项保持未完成。
3. `chat_history.md`
   - 追加第二批用户请求、资料下载、pypdf 批准、研究结论、交付文件、验证与未执行事项，不覆盖旧记录。

## 4. 写作决策

- PbtA 以 Apocalypse World 2e 为具体证据，不声称所有 PbtA 游戏骰制完全一致。
- FitD 的时钟只反映已确立的虚构状态，不让时钟脱离事实自动生成剧情。
- GUMSHOE 的“核心线索保障”与本项目坏骰不锁死原则一致，但不等于玩家自动理解真相。
- Ironsworn 的 Oracle 是上下文提示工具，不是完整 GM 模拟器；本项目随机结果也必须经权限和连续性校验。
- Mythic 只形成“公开证据支持的抽象机制表”，未知阈值与算法明确写“未核实”，不给伪精确实现。
- Fate 的 Aspect 不直接并入全球正典；只有经既有 A 级权限提交的事实才能影响权威状态，Compel 候选不能绕过案件审核或人工批准。

## 5. 验证标准

1. 三份专题报告均含来源、版本／公开范围、许可证、机制表、采用与不采用清单、证据限制。
2. PDF 结论能定位到已核实的物理页码；网页结论能定位到官方 URL 和章节。
3. 不包含来自非官方 Mythic 规则转述的阈值或算法。
4. 索引、todo 与 chat history 状态一致，第二批完成且第三批未开始。
5. 所有新增及修改 Markdown 均为 UTF-8 BOM＋CRLF，无意外覆盖旧对话。
6. 用只读脚本检查文件存在、BOM、CRLF、关键链接和必要章节；本批无代码变更，不运行游戏测试。
7. 最终回复列出变更文件、验证结果、未执行事项及官方 Sources。

## 6. 审批点

本规格沿用用户已确认的第二批研究计划。写入上述报告和状态更新前，需用户确认本次交付规格；确认后按 `Docs/design/tasks.md` 顺序执行，完成后停止，不自动开始第三批。

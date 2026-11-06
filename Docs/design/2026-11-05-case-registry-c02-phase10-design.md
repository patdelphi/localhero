# 第十阶段设计：C02 与跨案关联

- 创建日期：2026-11-05
- 状态：已完成（2026-11-05）
- 依据：[第八至第十三阶段路线图](2026-11-05-roadmap-phase8-13.md)、[当前状态](current-status.md)
- 范围：案件注册表、C02《最后一班配送》、跨案线索、前端案件入口、旧档兼容

## 1. 目标

在不改变 C01 既有事实、审计与回放结果的前提下，让同一程序按存档加载不同案件内容，并交付第二宗可完整游玩的 C02。

## 2. 关键假设

1. 一个存档只属于一个案件；C02 不读取 C01 存档状态，跨案关联通过共享人物、共享组织和带跨案标记的线索表达。
2. C01 内容保持字节级不变，仅通过 `CaseBundle` 包装；现有测试与真实存档继续有效。
3. C02 使用单一“日志覆盖”时钟，上限 3；沿用现有单时钟投影结构，不新增多时钟表。
4. 新档默认 C01；旧档缺失 `case_id` 时按 C01 处理。
5. 第十阶段新增 schema v7（`games.case_id`），第十二阶段迁移顺延为 v8。

## 3. 案件注册表

新增 `app/case_registry.py`，用不可变 `CaseBundle` 汇总一个案件的全部固定内容：

| 字段 | 说明 |
| --- | --- |
| `case_id` | 案件编号，如 `C01`、`C02` |
| `title` / `subtitle` | 前端展示名称与一句话简介 |
| `content_version` | 回放与审计使用的案件内容版本 |
| `start_phase` / `start_location` | 新档初始阶段与地点 |
| `clock_id` / `clock_label` / `clock_max` | 时钟语义与上限 |
| `plan_scope` | 局部计划作用域（C01 为 `c01`） |
| `commission_clue` / `commission_action` | 判断“已接案”的固定线索与行动 |
| `locations` / `clue_labels` / `clue_definitions` | 地点、线索 |
| `actions` / `action_metadata` | 行动目录与声明元数据 |
| `knowledge_declarations` / `local_plan_definitions` | 固定证词与到期计划 |
| `npc_initial_knowledge` / `autonomy_plan_definitions` / `autonomy_effect_definitions` / `scene_definitions` | NPC 自主与场景 |
| `endings` | 结局编号与展示名 |
| `initial_cognition()` | 新档初始认知生成函数 |
| `cross_case_links` | 跨案线索元数据 |

注册表提供：

```python
list_cases() -> list[dict]          # 新档界面的案件目录
get_case(case_id) -> CaseBundle     # 未知编号抛 ValueError
get_case_for_game(db, game_id)      # 读取 games.case_id 后解析，缺失按 C01
```

`case_content.py` 继续作为 C01 内容源，不搬家；`case_c02.py` 为新增内容模块。

## 4. 模块注入方式

所有原先直接导入 `case_content` 常量的模块增加可选 `case` 参数，默认值仍是 C01：

- `case_engine`: `initial_state`、`available_actions`、`action_by_id`、`public_state`、`resolve_action`
- `action_pipeline`: `prepare_action`、`prepare_recorded_action`、`build_structured_changes`、`apply_plan`、`make_audit`
- `local_simulation`: 到期计划定义与作用域
- `npc_decision` / `scene_director`: 传入固定定义与内容版本
- `narrative_context`: 地点描述
- `director`: 禁止词表（地点名与线索名）
- `model` / `llm_model`: 叙事模板查找与固定要点，改为优先使用当前案件行动内容
- `store`: `create_game` 写入案件与初始认知；`commit_action` 按 `games.case_id` 解析案件，用于场景校验与内容版本
- `replay_engine`: 按存档案件解析基线版本、行动目录与初始认知

默认参数保证既有调用与测试不变。

## 5. C02《最后一班配送》

### 5.1 地点

| 编号 | 名称 | 区域 |
| --- | --- | --- |
| `OC-01` | 灰区事务所 | 旧城区 |
| `HC-01` | 栖光里商业综合体 | 蜂巢区 |
| `HC-04` | 零工互助站 | 蜂巢区 |
| `HC-09` | 安澜工程调度点 | 蜂巢区 |

### 5.2 行动链

1. 事务所：接受/拒绝委托、询问周弥细节、前往栖光里。
2. 栖光里现场：查碰撞痕迹（现场路径）、查看商户与学校改道通知（现场路径）、调取配送终端记录（设备路径）。
3. 互助站：核对周弥的存储片、核实夜班配送员证词（劳动路径）、追查路线清洁日志（数据路径，可取得跨案线索）。
4. 工程调度点：核对十五分钟手动保持日志、追问顾北庭的灰度报告、对照地图版本。
5. 结局：个人复职、安全暂停、集体谈判。

必要线索采用 `necessary` 保障：碰撞事实、周弥指令、手动保持、地图版本差异均可通过替代路径获得，单次坏骰不永久断链。

### 5.3 结局

| 编号 | 名称 | 条件要点 |
| --- | --- | --- |
| `personal_reinstatement` | 个人复职 | 证明事故非周弥制造，接受取走存储片的警告 |
| `safety_pause` | 安全暂停 | 证明地图版本与保持超时，推动路线暂停与人流联动 |
| `collective_bargaining` | 集体谈判 | 互助会以证据换取正式安全协商渠道 |

### 5.4 跨案线索

C02 行动“追查路线清洁日志”可获得 `legacy_credential_trace`：

> 数澜清洁任务仍由苗雨旧凭证触发，操作者却是邵谦团队（关联 C01）。

该线索在 C02 内可用于结局条件，并在前端带“跨案”标记。C01 不新增行动或线索，避免回归风险；跨案关联以注册表元数据与 C02 内容引用表达。

## 6. 存储与迁移

- schema v7：`games` 新增 `case_id TEXT NOT NULL DEFAULT 'C01'`。
- 升级前保留 `pre-v7` 备份；`user_version=7`。
- 旧档读取时 `case_id` 为空或缺失统一按 `C01`。
- `replay_baselines.content_version` 继续按案件写入，C01 保持 `c01-1.3`。

## 7. API 与前端

- `GET /api/cases`：返回案件目录（编号、标题、简介、地点数、结局名、跨案标记）。
- `POST /api/games`：新增可选 `case_id`，默认 `C01`；未知编号返回 422。
- `GET /api/games/{id}`：返回 `game.case_id` 与案件公开状态。
- 新档区域增加案件选择；顶部显示案件标题；线索列表对 `cross_case` 线索加标记。

## 8. 回放与审计

- 回放按 `games.case_id` 解析行动目录、初始认知、内容版本与初始状态。
- 旧 C01 存档的基线版本仍为 `c01-1.3`，校验保持通过。
- C02 行动审计写入 `c02-1.0`；`case_facts.subject_id` 与 `clock_id` 使用案件对应值。

## 9. 测试计划（先写失败测试）

1. 注册表：C01/C02 可列出、未知编号报错、C01 内容版本不变。
2. 新档默认 C01；指定 C02 后案件标题、初始地点、时钟上限正确。
3. v7 迁移：旧库补列且默认 C01，连续初始化幂等。
4. C02 完整链：接受委托 → 现场/设备/劳动证据 → 三种结局各一条。
5. 坏骰保障：核心线索仍可获得，不出现永久断链。
6. 跨案线索：C02 取得 `legacy_credential_trace`，带跨案元数据。
7. API：案件目录、非法 case_id 422、C02 存档读取。
8. 回放：C01 旧流程与 C02 新流程均 `matched`。
9. 越权与隔离：C02 不能执行 C01 行动；C01 不能执行 C02 行动。
10. 导演与叙事：C02 行动可正常叙事，导演关闭时审计仍为 v3。

## 10. 验收标准

- 新档可选择 C01 或 C02，两案均可从开场玩到结局。
- C01 既有 146 项测试全部通过，审计与回放结果不变。
- C02 三种结局可达；跨案线索可认知并带标记。
- 全量测试、Python `compileall`、JavaScript `node --check`、`git diff --check` 通过。
- 自动测试与浏览器验收只使用临时数据库，不修改真实 `data/games.db`。

## 11. 边界

- 不实现 C03、全城地图、跨存档全局档案。
- 不实现多时钟、分支存档与部署配置。
- 不自动执行 Git commit / push。

# 第十二阶段：分支存档与推演设计

- 日期：2026-11-05
- 状态：已完成
- 对应路线图：第十二阶段「分支存档与推演」
- schema：v8

## 1. 目标

允许玩家从任意已记录行动分叉出新存档，原存档全程只读；分支可独立继续游玩、独立回放校验，并提供分支树与关键状态对比。删除采用可恢复的软删除归档。

## 2. 关键决策

| 决策 | 选择 | 原因 |
| --- | --- | --- |
| 删除策略 | 软删除，`branch_status='archived'` | 保留历史与回放能力，可随时恢复 |
| 分叉点 | 任意已记录行动之后 | 与时间线“校验至此”一致，无需额外快照表 |
| 重建方式 | 确定性重放源存档前缀 | 复用既有回放规则，避免物理主键和时间戳污染 |
| 分支数量 | 单存档直属分支上限 10 | 防止本地库无界增长 |
| 分支树节点 | 单次返回上限 40 | 防止界面渲染过大 |

已确认：归档必须显式确认；根存档不能归档。

## 3. schema v8

`games` 新增列：

| 列 | 类型 | 作用 |
| --- | --- | --- |
| `parent_game_id` | TEXT，外键指向 `games(id)` | 父存档 |
| `fork_action_id` | TEXT | 源存档中的分叉行动编号 |
| `fork_action_index` | INTEGER | 分叉行动在源存档中的序号（1 起） |
| `branch_label` | TEXT | 分支名称，默认“分支 N” |
| `branch_status` | TEXT，默认 `active` | `active` / `archived` |
| `branch_created_at` | TEXT | UTC 秒级创建时间 |

升级前自动备份为 `{db.name}.pre-v8.bak`；补列使用 `ALTER TABLE games ADD COLUMN`，不重建表。

## 4. 重建流程

`ReplayEngine.rebuild_prefix(database, target_game_id, game_id, through_action_id)`：

1. 只读提取源存档一致性快照；
2. 校验基线、事件白名单与全部前缀行动；
3. 在目标存档恢复基线（`games`、开场事件、初始认知、`case_states`、`replay_baselines`）；
4. 逐个重放前缀行动，使用保存的命令、意图与骰点；
5. 返回源行动到新行动的编号映射，以及需要复制的 `narrative_completed` 事件。

机械事件（`case_changed`、`social_changed`、`scene_activated`、`local_simulation_advanced`、`offscreen_activity`）由重放自行生成，不复制源存档，避免重复写入。

## 5. 分支生命周期

- 创建：校验父存档未归档、名称不超过 40 字符、直属分支未超限；任一写入失败时按外键顺序清理半成品。
- 切换：前端读取目标存档即切换，不修改任何存档。
- 归档：`POST /api/games/{id}/branch/archive`，必须 `confirm=true`。
- 恢复：`POST /api/games/{id}/branch/restore`，必须 `confirm=true`。
- 归档只改 `branch_status`，所有行动、事件与认知数据保留。

## 6. 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/games/{game_id}/branches` | 创建分支，请求体含 `fork_action_id` 与可选 `label` |
| GET | `/api/games/{game_id}/branches` | 返回根节点到当前节点的分支树 |
| POST | `/api/games/{branch_id}/branch/archive` | 归档分支，需 `confirm=true` |
| POST | `/api/games/{branch_id}/branch/restore` | 恢复分支，需 `confirm=true` |

分支树节点包含：存档编号、父存档、分叉行动与序号、名称、状态、是否根/当前，以及阶段、位置、Clock、结局、状态版本、线索数、行动数。

## 7. 界面

- 历史时间线每个行动新增“从此分叉”。
- 新增“分支存档”折叠面板，展示分支树与各节点关键状态摘要。
- 支持“切换至此”“归档”“恢复”；归档与恢复使用浏览器确认弹窗。
- 创建分支后自动进入新分支并刷新面板。

## 8. 测试

`tests/test_phase12.py` 共 12 项：

1. v7 → v8 迁移、补列与备份；
2. 分支重建前缀状态且源存档关键行完全不变；
3. 分支继续行动不影响源存档；
4. 分支可独立回放并通过校验；
5. 分支树节点与状态摘要；
6. 二级分支；
7. 归档必须确认且可恢复；
8. 根存档禁止归档；
9. 未知分叉行动被拒绝且不留残行；
10. 直属分支上限；
11. API 创建、列表、归档、恢复全流程；
12. 缺少分叉点时返回 422。

## 9. 验证结果

- 全量测试 178 项通过。
- Python `compileall`、JavaScript `node --check`、`git diff --check` 通过。
- 浏览器验收 6 项全部 PASS：加载存档、从第 2 个行动分叉、分支树与状态对比、归档、恢复、切回根存档。
- 验收使用临时数据库，未修改真实存档。

## 10. 边界

- 不做云端同步、多人协作与实时合并。
- 不做分支重命名与物理删除；归档即可恢复。
- 分支日程与城市切片按自身行动条数独立推进，不共享源存档时间线。

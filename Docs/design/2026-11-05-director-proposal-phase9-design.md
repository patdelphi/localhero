# 第九阶段设计：AI 受限情节演进（Director Proposal）

- 创建日期：2026-11-05
- 状态：实施中
- 依据：[第八至第十三阶段路线图](2026-11-05-roadmap-phase8-13.md)、[当前状态](current-status.md)、[第八阶段设计](2026-11-05-narrative-context-phase8-design.md)

## 1. 目标

在固定案件框架内允许 AI 提出一个有界的“情节节拍”，由程序白名单校验后才写入，且全程可审计、可回放、可关闭。AI 只参与“提出”，不参与“批准”。

本阶段只开放一种节拍：`environment_complication`（环境复杂化）。

## 2. 边界

- 提案不能新增人物、地点、线索、结局、数值、判定或时间。
- 效果只能引用固定白名单中的公开环境提示，机械变化恒为零。
- 同一节拍每档最多接受一次；触发需满足行动冷却。
- 关闭后审计与事件结构与第八阶段完全一致，不写 `director` 字段。
- 失败提案不产生任何写入；接受提案与行动在同一事务提交。

## 3. 数据结构

### 3.1 提案（模型输出）

```json
{
  "beat_type": "environment_complication",
  "effect_id": "env.rain_gutter",
  "target_action": "当前行动编号",
  "reason": "环境出现新的公开变化"
}
```

模型只能选择 `effect_id`，不能自带展示文本。展示文本一律来自白名单。

### 3.2 审计 v4

仅在功能开启时写入：

```json
{
  "audit_version": 4,
  "director": {
    "version": "director-1",
    "enabled": true,
    "trigger": {"checked": true, "rule_id": "director.trigger_ready",
                "actions_since_last": 5, "interval": 5},
    "proposal": {"proposal_id": "...", "beat_type": "...", "effect_id": "...",
                 "target_action": "...", "reason": "...", "source": "provider"},
    "validation": {"accepted": true, "rule_id": "director.accepted",
                   "reason": "提案通过白名单与冷却校验"},
    "accepted": true,
    "effect": {"beat_type": "...", "effect_id": "...", "text": "...",
               "clock_delta": 0, "fact_changes": 0}
  }
}
```

功能关闭时仍为 `audit_version=3`，且不存在 `director` 键，保证与第八阶段一致。

### 3.3 事件

接受后写入一条 `director_beat` 事件，与行动同事务：

```json
{"beat_type": "...", "effect_id": "...", "text": "...",
 "target_action": "...", "proposal_id": "...", "source": "...", "reason": "..."}
```

## 4. 校验规则

| 规则 | 拒绝条件 |
| --- | --- |
| `director.proposal_invalid` | 提案不是对象或缺少必要字段 |
| `director.beat_type_not_allowed` | 节拍类型不在白名单 |
| `director.effect_not_allowed` | 效果编号不在白名单 |
| `director.effect_beat_mismatch` | 效果不属于该节拍 |
| `director.target_mismatch` | 目标行动与当前行动不一致 |
| `director.reason_rejected` | 理由超长、含数字、人物名、地点、线索或敏感词 |
| `director.mechanical_change_rejected` | 效果声明任何 Clock／事实变化 |
| `director.no_repeat_beat` | 同档已接受过同一节拍 |

触发规则：

- `AI_DIRECTOR_ENABLED` 默认关闭。
- `AI_DIRECTOR_INTERVAL` 默认 5，限制 2—50。
- 距离上一次接受节拍至少间隔 N 次已提交行动。
- 同档每种节拍最多接受 `MAX_BEATS_PER_GAME=1` 次。

## 5. 可回放性

- 回放不调用模型，只读取行动审计中已保存的 `director` 段。
- 回放按同一 `commit_action` 事务重新写入 `director_beat` 事件。
- 规范化快照新增 `director_beats` 投影，参与一致性比较。
- 被拒绝的提案只出现在审计中，不写事件，不影响状态。

## 6. 接口与界面

- `GET /api/games/{game_id}/director`：返回开关、间隔、可用节拍。
- `POST /api/games/{game_id}/director`：会话内切换开关，不写存档、不推进游戏。
- 前端在存档栏显示“情节导演：开／关”，接受节拍以“情节节拍”事件展示。
- 审计面板新增“情节导演”段落，展示提出者、理由、校验规则与最终效果。

## 7. 验收

- 越权、重复、目标不符、含数字或私密词的提案全部拒绝且无部分写入。
- 接受提案写入一条事件与审计 v4。
- 开关关闭时审计、事件与第八阶段一致。
- 接受提案后的存档可确定性回放通过。
- 审计能回答“谁提出、为何接受”。

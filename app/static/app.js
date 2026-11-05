/* 程序说明：连接本地 FastAPI，处理行动、只读审计、历史时间线与隔离机械回放。 */
"use strict";

const state = {
  gameId: null,
  selectedActionId: null,
  preview: null,
  pendingRequest: null,
  pendingNarrativeId: null,
  auditOpen: false,
  timelineOpen: false,
  replayBusy: false,
  replayAvailable: true,
  editingHypothesisId: null,
};

const elements = {
  entry: document.querySelector("#entry-panel"),
  game: document.querySelector("#game-panel"),
  entryError: document.querySelector("#entry-error"),
  actionError: document.querySelector("#action-error"),
  actionInput: document.querySelector("#action-input"),
  submit: document.querySelector("#submit-action"),
  confirm: document.querySelector("#confirm-action"),
  cancel: document.querySelector("#cancel-action"),
  retry: document.querySelector("#retry-action"),
  actionState: document.querySelector("#action-state"),
  actionPreview: document.querySelector("#action-preview"),
  sceneLog: document.querySelector("#scene-log"),
  rollResult: document.querySelector("#roll-result"),
  caseActions: document.querySelector("#case-actions"),
  auditPanel: document.querySelector("#audit-panel"),
  auditList: document.querySelector("#audit-list"),
  toggleAudit: document.querySelector("#toggle-audit"),
  timelinePanel: document.querySelector("#timeline-panel"),
  timelineList: document.querySelector("#timeline-list"),
  timelineNote: document.querySelector("#timeline-note"),
  toggleTimeline: document.querySelector("#toggle-timeline"),
  verifyLatest: document.querySelector("#verify-latest"),
  replayResult: document.querySelector("#replay-result"),
  knowledgeList: document.querySelector("#knowledge-list"),
  planList: document.querySelector("#plan-list"),
  historyList: document.querySelector("#history-list"),
  hypothesisList: document.querySelector("#hypothesis-list"),
  hypothesisForm: document.querySelector("#hypothesis-form"),
  hypothesisInput: document.querySelector("#hypothesis-input"),
  hypothesisError: document.querySelector("#hypothesis-error"),
  submitHypothesis: document.querySelector("#submit-hypothesis"),
  cancelHypothesis: document.querySelector("#cancel-hypothesis"),
};

const phaseLabels = {
  unoffered: "未接单",
  deferred: "委托暂缓",
  active: "调查中",
  closed: "已结案",
};

const knowledgeKindLabels = {
  observation: "观察",
  memory: "记忆",
  testimony: "证词",
};

const holderLabels = {
  player: "你",
  fang_sheng: "方笙",
  shao_qian: "邵谦",
  lin_yanzhou: "林砚舟",
  a_luo: "阿洛",
};

const historyKindLabels = {
  relationship: "公开关系",
  condition: "社会状态",
  plan: "固定计划",
};

const planLabels = {
  fangsheng_followup: "方笙整理旧排班补充",
};

const accuracyLabels = {
  direct: "直接感知",
  honest: "诚实陈述",
  misleading: "可能误导",
  unknown: "准确性未知",
};

const precisionLabels = {
  exact: "清晰",
  vague: "模糊",
  fragmentary: "破碎",
  unknown: "精度未知",
};

const declarationLabels = {
  target: "目标",
  method: "方法",
  position: "处境",
  effect: "效果",
  cost: "代价方向",
  modifier_source: "修正来源",
};

/** 所有 API 都检查 HTTP 状态并提取服务端错误，不静默失败。 */
async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch (error) {
    throw new Error("无法连接本地游戏服务，请确认服务仍在运行。");
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.detail || `本地服务返回错误 ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function setBusy(busy, label = "等待输入") {
  elements.submit.disabled = busy;
  elements.retry.disabled = busy;
  elements.confirm.disabled = busy || !state.preview;
  document.querySelectorAll("#case-actions button").forEach((button) => {
    button.disabled = busy;
  });
  elements.actionState.textContent = label;
}

function showGame(gameId) {
  state.gameId = gameId;
  localStorage.setItem("grey-zone-game-id", gameId);
  elements.entry.hidden = true;
  elements.game.hidden = false;
  document.querySelector("#game-id").textContent = gameId;
}

function publicSceneText(scene) {
  const texts = {
    fangsheng_remote_schedule: "方笙通过远程联系补充了旧排班中的共享账户备注。",
    fangsheng_remote_reminder: "方笙通过远程联系给出了一条谨慎的旧排班提醒。",
  };
  return texts[scene.scene_id] || "公开远程场景已激活";
}

function renderEvent(event) {
  const article = document.createElement("article");
  const label = document.createElement("span");
  const body = document.createElement("div");
  article.className = "scene-event";
  label.className = "event-label";
  body.className = "event-body";

  if (event.kind === "game_started") {
    label.textContent = "开场";
    body.textContent = event.payload.text;
  } else if (event.kind === "action_committed") {
    article.classList.add("player-event");
    label.textContent = "你的行动";
    body.textContent = event.payload.input;
    if (event.payload.roll) {
      const small = document.createElement("small");
      const roll = event.payload.roll;
      small.textContent = `2D6 [${roll.dice.join(" + ")}] + ${roll.modifier} = ${roll.total}`;
      body.appendChild(small);
    }
  } else if (event.kind === "case_changed") {
    label.textContent = "案件变化";
    const parts = [`阶段：${phaseLabels[event.payload.phase] || event.payload.phase}`];
    parts.push(`项目清理：${event.payload.clock} / 4`);
    parts.push(`游戏内时间：${event.payload.world_time ?? 0}`);
    if (event.payload.clues?.length) parts.push(`线索：${event.payload.clues.length} 条`);
    if (event.payload.ending) parts.push(`结局：${event.payload.ending}`);
    body.textContent = parts.join(" · ");
  } else if (event.kind === "social_changed") {
    label.textContent = "社会变化";
    body.textContent = event.payload.changes?.join("；") || "公开社会关系已更新";
  } else if (event.kind === "local_simulation_advanced") {
    label.textContent = "局部推进";
    body.textContent = event.payload.changes?.join("；") || "固定计划或短期状态已到期";
  } else if (event.kind === "scene_activated") {
    label.textContent = "远程场景";
    body.textContent = publicSceneText(event.payload);
  } else {
    label.textContent = "场景";
    body.textContent = event.payload.text || "事件已记录";
  }
  article.append(label, body);
  return article;
}

function renderRoll(roll) {
  elements.rollResult.replaceChildren();
  elements.rollResult.hidden = !roll;
  if (!roll) return;
  const outcome = { success: "成功", partial: "有代价成功", escalation: "局势升级" };
  const text = document.createElement("div");
  const strong = document.createElement("strong");
  strong.textContent = outcome[roll.outcome];
  text.append(`2D6 [${roll.dice.join(" + ")}] + ${roll.modifier} = ${roll.total} · `, strong);
  elements.rollResult.appendChild(text);
}

function renderCase(caseState) {
  document.querySelector("#location-index").textContent = `LOCATION / ${caseState.location}`;
  document.querySelector("#location-name").textContent = caseState.location_name;
  document.querySelector("#case-location").textContent = `${caseState.location} · ${caseState.district}`;
  document.querySelector("#case-phase").textContent = phaseLabels[caseState.phase] || caseState.phase;
  document.querySelector("#case-clock").textContent = `${caseState.clock} / ${caseState.clock_max}`;
  document.querySelector("#case-world-time").textContent = caseState.world_time;
  document.querySelector("#case-ending").textContent = caseState.ending || "尚未结案";
  document.querySelector("#case-revision").textContent = caseState.revision;
  renderPlans(caseState.plans || []);

  const clueList = document.querySelector("#clue-list");
  clueList.replaceChildren();
  if (!caseState.clues.length) {
    const empty = document.createElement("li");
    empty.textContent = "暂无线索";
    empty.className = "empty-clue";
    clueList.appendChild(empty);
  } else {
    caseState.clues.forEach((clue) => {
      const item = document.createElement("li");
      item.textContent = clue.label;
      clueList.appendChild(item);
    });
  }

  elements.caseActions.replaceChildren();
  caseState.actions.forEach((action) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = action.label;
    button.addEventListener("click", () => {
      state.selectedActionId = action.id;
      elements.actionInput.value = action.label;
      clearPreview();
      elements.actionInput.focus();
    });
    elements.caseActions.appendChild(button);
  });
}

function renderPlans(items) {
  elements.planList.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("li");
    empty.className = "board-empty";
    empty.textContent = "暂无公开计划";
    elements.planList.appendChild(empty);
    return;
  }
  items.forEach((item) => {
    const entry = document.createElement("li");
    const content = document.createElement("p");
    const meta = document.createElement("small");
    content.textContent = planLabels[item.plan_id] || item.plan_id;
    meta.textContent = `${holderLabels[item.holder_id] || item.holder_id} · 到期时间 ${item.due_time} · ${item.status === "completed" ? "已完成" : "待处理"}`;
    entry.append(content, meta);
    elements.planList.appendChild(entry);
  });
}

function renderHistory(items) {
  elements.historyList.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("li");
    empty.className = "board-empty";
    empty.textContent = "暂无人物履历";
    elements.historyList.appendChild(empty);
    return;
  }
  items.forEach((item) => {
    const entry = document.createElement("li");
    const content = document.createElement("p");
    const meta = document.createElement("small");
    content.textContent = item.content;
    meta.textContent = `${historyKindLabels[item.kind] || item.kind} · ${holderLabels[item.holder_id] || item.holder_id} · 来源事件 #${item.source_event_id}`;
    entry.append(content, meta);
    elements.historyList.appendChild(entry);
  });
}

function renderKnowledge(items) {
  elements.knowledgeList.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("li");
    empty.className = "board-empty";
    empty.textContent = "暂无观察或证词";
    elements.knowledgeList.appendChild(empty);
    return;
  }
  items.forEach((item) => {
    const entry = document.createElement("li");
    const content = document.createElement("p");
    const meta = document.createElement("small");
    content.textContent = item.content;
    const correction = item.has_correction ? " · 已有纠正" : "";
    meta.textContent = `${knowledgeKindLabels[item.kind] || item.kind} · ${holderLabels[item.holder_id] || item.holder_id} · ${accuracyLabels[item.accuracy] || item.accuracy} · ${precisionLabels[item.precision] || precisionLabels.unknown}${correction} · 来源事件 #${item.source_event_id}`;
    entry.append(content, meta);
    elements.knowledgeList.appendChild(entry);
  });
}

function resetHypothesisForm() {
  state.editingHypothesisId = null;
  elements.hypothesisInput.value = "";
  elements.submitHypothesis.textContent = "新增假设";
  elements.cancelHypothesis.hidden = true;
}

function renderHypotheses(items) {
  elements.hypothesisList.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("li");
    empty.className = "board-empty";
    empty.textContent = "暂无个人假设";
    elements.hypothesisList.appendChild(empty);
    return;
  }
  items.forEach((hypothesis) => {
    const entry = document.createElement("li");
    const content = document.createElement("p");
    const controls = document.createElement("div");
    const edit = document.createElement("button");
    const remove = document.createElement("button");
    content.textContent = hypothesis.text;
    controls.className = "hypothesis-item-controls";
    edit.type = "button";
    edit.className = "text-button";
    edit.textContent = "编辑";
    edit.addEventListener("click", () => {
      state.editingHypothesisId = hypothesis.id;
      elements.hypothesisInput.value = hypothesis.text;
      elements.submitHypothesis.textContent = "保存修改";
      elements.cancelHypothesis.hidden = false;
      elements.hypothesisInput.focus();
    });
    remove.type = "button";
    remove.className = "text-button danger-button";
    remove.textContent = "删除";
    remove.addEventListener("click", () => removeHypothesis(hypothesis.id));
    controls.append(edit, remove);
    entry.append(content, controls);
    elements.hypothesisList.appendChild(entry);
  });
}

async function loadCaseBoard() {
  const [knowledge, history, hypotheses] = await Promise.all([
    api(`/api/games/${state.gameId}/knowledge`),
    api(`/api/games/${state.gameId}/character-history`),
    api(`/api/games/${state.gameId}/hypotheses`),
  ]);
  renderKnowledge(knowledge.items);
  renderHistory(history.items);
  renderHypotheses(hypotheses.items);
}

async function saveHypothesis(event) {
  event.preventDefault();
  const text = elements.hypothesisInput.value.trim();
  if (!text) return;
  elements.hypothesisError.textContent = "";
  elements.submitHypothesis.disabled = true;
  try {
    const path = state.editingHypothesisId
      ? `/api/games/${state.gameId}/hypotheses/${state.editingHypothesisId}`
      : `/api/games/${state.gameId}/hypotheses`;
    await api(path, {
      method: state.editingHypothesisId ? "PATCH" : "POST",
      body: JSON.stringify({ text }),
    });
    resetHypothesisForm();
    await loadCaseBoard();
  } catch (error) {
    elements.hypothesisError.textContent = error.message;
  } finally {
    elements.submitHypothesis.disabled = false;
  }
}

async function removeHypothesis(hypothesisId) {
  elements.hypothesisError.textContent = "";
  try {
    await api(`/api/games/${state.gameId}/hypotheses/${hypothesisId}`, { method: "DELETE" });
    if (state.editingHypothesisId === hypothesisId) resetHypothesisForm();
    await loadCaseBoard();
  } catch (error) {
    elements.hypothesisError.textContent = error.message;
  }
}

async function loadGame(gameId) {
  const data = await api(`/api/games/${gameId}`);
  showGame(gameId);
  document.querySelector("#protagonist-name").textContent = data.game.protagonist;
  document.querySelector("#protagonist-mark").textContent = data.game.protagonist.slice(0, 1);
  document.querySelector("#roll-count").textContent = `${data.game.roll_count} 次`;
  renderCase(data.case);
  elements.sceneLog.replaceChildren(...data.events.map(renderEvent));
  elements.sceneLog.lastElementChild?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  await loadCaseBoard();
  if (state.auditOpen) await loadAudit();
  if (state.timelineOpen) await loadTimeline();
}

async function createGame(event) {
  event.preventDefault();
  elements.entryError.textContent = "";
  try {
    const protagonist = document.querySelector("#protagonist").value;
    const game = await api("/api/games", {
      method: "POST",
      body: JSON.stringify({ protagonist }),
    });
    await loadGame(game.id);
  } catch (error) {
    elements.entryError.textContent = error.message;
  }
}

async function loadExistingGame(event) {
  event.preventDefault();
  elements.entryError.textContent = "";
  const gameId = document.querySelector("#load-id").value.trim();
  try {
    await loadGame(gameId);
  } catch (error) {
    elements.entryError.textContent = error.message;
  }
}

function clearPreview() {
  state.preview = null;
  elements.actionPreview.hidden = true;
  elements.confirm.disabled = true;
}

function renderPreview(preview) {
  const declaration = document.querySelector("#preview-declaration");
  declaration.replaceChildren();
  Object.entries(declarationLabels).forEach(([key, label]) => {
    const term = document.createElement("dt");
    const value = document.createElement("dd");
    term.textContent = label;
    value.textContent = preview.declaration[key];
    declaration.append(term, value);
  });
  document.querySelector("#preview-revision").textContent = `状态版本 ${preview.revision}`;
  document.querySelector("#preview-reason").textContent = preview.reason || "预览不掷骰；确认后才提交事实。";
  elements.actionPreview.hidden = false;

  if (!preview.can_submit) {
    state.preview = null;
    elements.confirm.disabled = true;
    return;
  }
  const selectedId = preview.selected_action.action_id;
  const isCaseAction = preview.candidates.some((item) => item.action_id === selectedId);
  state.preview = {
    text: preview.normalized_input,
    action_id: isCaseAction ? selectedId : null,
    expected_revision: preview.revision,
  };
  elements.confirm.disabled = false;
}

async function previewAction(event) {
  event.preventDefault();
  elements.actionError.textContent = "";
  const text = elements.actionInput.value.trim();
  if (!text) return;
  clearPreview();
  setBusy(true, "生成只读预览");
  try {
    const preview = await api(`/api/games/${state.gameId}/actions/preview`, {
      method: "POST",
      body: JSON.stringify({ text, action_id: state.selectedActionId }),
    });
    renderPreview(preview);
    elements.actionState.textContent = preview.can_submit ? "等待确认" : "行动不可提交";
  } catch (error) {
    elements.actionError.textContent = error.message;
    elements.actionState.textContent = "等待输入";
  } finally {
    setBusy(false, state.preview ? "等待确认" : "等待输入");
  }
}

async function confirmAction() {
  if (!state.preview && !state.pendingRequest) return;
  elements.actionError.textContent = "";
  if (!state.pendingRequest) {
    state.pendingRequest = { ...state.preview, request_id: crypto.randomUUID() };
  }
  setBusy(true, "程序提交中");
  try {
    const result = await api(`/api/games/${state.gameId}/actions`, {
      method: "POST",
      body: JSON.stringify(state.pendingRequest),
    });
    state.pendingRequest = null;
    state.selectedActionId = null;
    clearPreview();
    elements.actionInput.value = "";
    renderRoll(result.roll);
    if (result.status === "narrative_pending") {
      state.pendingNarrativeId = result.action_id;
      elements.retry.hidden = false;
    } else {
      state.pendingNarrativeId = null;
      elements.retry.hidden = true;
    }
    await loadGame(state.gameId);
  } catch (error) {
    elements.actionError.textContent = error.message;
    if (error.status === 409) {
      state.pendingRequest = null;
      clearPreview();
      elements.actionError.textContent += " 请重新预览，不会自动换骰或重试。";
    }
  } finally {
    setBusy(false, state.pendingNarrativeId ? "事实已提交，叙事待重试" : "等待输入");
  }
}

async function retryNarrative() {
  if (!state.pendingNarrativeId) return;
  setBusy(true, "重新生成叙事");
  elements.actionError.textContent = "";
  try {
    const result = await api(
      `/api/games/${state.gameId}/actions/${state.pendingNarrativeId}/retry`,
      { method: "POST" },
    );
    if (result.status === "complete") {
      state.pendingNarrativeId = null;
      elements.retry.hidden = true;
    }
    await loadGame(state.gameId);
  } catch (error) {
    elements.actionError.textContent = error.message;
  } finally {
    setBusy(false);
  }
}

function auditSection(parent, title, lines) {
  const section = document.createElement("section");
  const heading = document.createElement("h4");
  const list = document.createElement("ul");
  heading.textContent = title;
  lines.forEach((line) => {
    const item = document.createElement("li");
    item.textContent = line;
    list.appendChild(item);
  });
  section.append(heading, list);
  parent.appendChild(section);
}

function renderAudit(entries) {
  elements.auditList.replaceChildren();
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "audit-note";
    empty.textContent = "尚无行动审计。";
    elements.auditList.appendChild(empty);
    return;
  }
  entries.forEach((entry) => {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    const audit = entry.audit || { audit_version: "legacy" };
    summary.textContent = `${entry.input_text} · ${entry.status} · ${audit.audit_version}`;
    details.appendChild(summary);
    if (audit.audit_version === "legacy") {
      auditSection(details, "历史数据", ["legacy：旧行动没有候选与规则轨迹，未补造审计。"]);
      elements.auditList.appendChild(details);
      return;
    }
    auditSection(details, "候选与排除", audit.candidates.map((item) => (
      `${item.label}：${item.eligible ? "可用" : item.excluded_reasons.join("；")}`
    )));
    auditSection(details, "选择与管线", [
      `${audit.selected_action.action_id} · ${audit.selected_action.selection_source}`,
      ...audit.pipeline.map((step) => `${step.stage} / ${step.rule_id}：${step.result}`),
    ]);
    auditSection(details, "行动声明", Object.entries(declarationLabels).map(
      ([key, label]) => `${label}：${audit.declaration[key]}`,
    ));
    auditSection(details, "权限与版本", [
      `${audit.permission.fact_level} · ${audit.permission.allowed ? "允许" : "拒绝"} · ${audit.permission.reason}`,
      `规则 ${audit.rules_version} · 内容 ${audit.content_version}`,
      `状态版本 ${audit.state_revision.before} → ${audit.state_revision.after}`,
      `审计状态 ${audit.status}`,
    ]);
    auditSection(details, "随机", [audit.random
      ? `种子 ${audit.random.seed} · 序号 ${audit.random.sequence} · [${audit.random.dice.join(" + ")}] + ${audit.random.modifier} = ${audit.random.total} · ${audit.random.outcome}`
      : "本次行动未掷骰"]);
    // 仅展示服务端已裁剪的公开证词及其公开纠正目标。
    const cognitionLines = (audit.cognition?.records || [])
      .filter((item) => item.kind === "testimony")
      .map((item) => {
        const correction = item.corrects_record_id
          ? ` · 纠正公开证词 ${item.corrects_record_id}`
          : "";
        return `${holderLabels[item.holder_id] || item.holder_id} · ${precisionLabels[item.precision] || precisionLabels.unknown}：${item.content}${correction}`;
      });
    if (cognitionLines.length) auditSection(details, "认知与纠正", cognitionLines);
    const autonomy = audit.autonomy || { responses: [], decisions: [], scenes: [] };
    const autonomyLines = [
      ...autonomy.responses.map((item) => `NPC回应：${item.response_kind}`),
      ...autonomy.decisions.map((item) => `最终候选：${item.selected_candidate_id || "无"}`),
      ...autonomy.scenes.map((item) => `场景：${publicSceneText(item)}`),
    ];
    if (autonomyLines.length) auditSection(details, "NPC回应与场景", autonomyLines);
    auditSection(details, "关联事件", entry.events.map(
      (event) => `#${event.id} ${event.kind}`,
    ));
    elements.auditList.appendChild(details);
  });
}

async function loadAudit() {
  const data = await api(`/api/games/${state.gameId}/audit?limit=50`);
  renderAudit(data.items);
}

function timelineEventText(event) {
  if (event.kind === "case_changed") {
    const parts = [
      `案件变化：${phaseLabels[event.phase] || event.phase || "状态已更新"}`,
      `位置 ${event.location || "未变"}`,
      `项目清理 ${event.clock ?? 0} / 4`,
      `时间 ${event.world_time ?? 0}`,
    ];
    if (event.ending) parts.push(`结局：${event.ending}`);
    return parts.join(" · ");
  }
  if (event.kind === "social_changed") {
    return `社会变化：${event.changes?.join("；") || "公开关系已更新"}`;
  }
  if (event.kind === "local_simulation_advanced") {
    return `局部推进：${event.changes?.join("；") || "固定事项已到期"}`;
  }
  if (event.kind === "scene_activated") return publicSceneText(event);
  if (event.kind === "narrative_completed") return event.text || "叙事已完成";
  if (event.kind.startsWith("legacy_")) return "旧档迁移记录（未补造历史）";
  return "行动已提交";
}

function setReplayBusy(busy) {
  state.replayBusy = busy;
  elements.verifyLatest.disabled = busy || !state.replayAvailable;
  elements.timelineList.querySelectorAll("[data-replay-action]").forEach((button) => {
    button.disabled = busy || !state.replayAvailable;
  });
}

function renderReplayResult(result) {
  elements.replayResult.classList.toggle("mismatch", result.status === "mismatched");
  if (result.status === "matched") {
    elements.replayResult.textContent = `一致：已独立重算并核对 ${result.checked_actions} 个行动，未发现机械差异。`;
    return;
  }
  if (result.status === "unavailable") {
    elements.replayResult.textContent = `无法校验：${result.reason.message}（${result.reason.code}）`;
    return;
  }
  const mismatch = result.first_mismatch;
  const paths = mismatch.differences.map((difference) => (
    difference.redacted ? "私密状态（内容已隐藏）" : difference.path
  ));
  elements.replayResult.textContent = [
    `发现不一致：首个差异位于第 ${mismatch.action_index} 个行动“${mismatch.input}”。`,
    `已完整核对前 ${result.checked_actions} 个行动。`,
    `差异字段：${paths.join("；")}`,
  ].join("\n");
}

function renderTimeline(data) {
  state.replayAvailable = data.baseline.available;
  elements.timelineNote.textContent = state.replayAvailable
    ? `基线 ${data.baseline.rules_version} / ${data.baseline.content_version}。机械校验不调用模型、不重新掷骰、不修改当前存档。`
    : "缺少初始基线，仅可查看历史；此旧档无法执行机械回放。";
  elements.replayResult.textContent = "";
  elements.replayResult.classList.remove("mismatch");
  elements.timelineList.replaceChildren();

  data.items.forEach((item) => {
    const article = document.createElement("article");
    const heading = document.createElement("h3");
    article.className = "timeline-item";
    if (item.kind === "game_started") {
      heading.textContent = "开场";
      const text = document.createElement("p");
      text.textContent = item.text;
      article.append(heading, text);
    } else if (item.kind === "action") {
      heading.textContent = `行动 ${item.action_index} · ${item.input}`;
      const meta = document.createElement("small");
      const revisions = item.revision_after === null || item.revision_after === undefined
        ? "旧记录无版本"
        : `状态版本 ${item.revision_before} → ${item.revision_after}`;
      meta.textContent = `${item.selected_action.label || item.selected_action.kind} · ${item.status} · 游戏内时间 ${item.world_time} · ${revisions}`;
      article.append(heading, meta);

      if (item.roll) {
        const roll = document.createElement("p");
        roll.textContent = `2D6 [${item.roll.dice.join(" + ")}] + ${item.roll.modifier} = ${item.roll.total} · ${item.roll.outcome}`;
        article.appendChild(roll);
      }
      item.events.forEach((event) => {
        const text = document.createElement("p");
        text.textContent = timelineEventText(event);
        article.appendChild(text);
      });
      if (item.narrative) {
        const narrative = document.createElement("p");
        narrative.textContent = item.narrative;
        article.appendChild(narrative);
      }
      const verify = document.createElement("button");
      verify.type = "button";
      verify.className = "text-button";
      verify.dataset.replayAction = item.action_id;
      verify.textContent = "校验至此";
      verify.disabled = state.replayBusy || !state.replayAvailable;
      verify.addEventListener("click", () => verifyReplay(item.action_id));
      article.appendChild(verify);
    } else {
      heading.textContent = "旧档迁移";
      const text = document.createElement("p");
      text.textContent = timelineEventText(item.event);
      article.append(heading, text);
    }
    elements.timelineList.appendChild(article);
  });
  setReplayBusy(state.replayBusy);
}

async function loadTimeline() {
  const data = await api(`/api/games/${state.gameId}/timeline`);
  renderTimeline(data);
}

async function verifyReplay(throughActionId = null) {
  if (state.replayBusy || !state.replayAvailable) return;
  setReplayBusy(true);
  elements.replayResult.classList.remove("mismatch");
  elements.replayResult.textContent = "正在独立重算；不会调用模型或写入当前存档。";
  try {
    const result = await api(`/api/games/${state.gameId}/replay/verify`, {
      method: "POST",
      body: JSON.stringify(throughActionId ? { through_action_id: throughActionId } : {}),
    });
    renderReplayResult(result);
  } catch (error) {
    elements.replayResult.textContent = `校验请求失败：${error.message}`;
  } finally {
    setReplayBusy(false);
  }
}

document.querySelector("#new-game-form").addEventListener("submit", createGame);
document.querySelector("#load-game-form").addEventListener("submit", loadExistingGame);
document.querySelector("#action-form").addEventListener("submit", previewAction);
elements.hypothesisForm.addEventListener("submit", saveHypothesis);
elements.cancelHypothesis.addEventListener("click", resetHypothesisForm);
elements.confirm.addEventListener("click", confirmAction);
elements.cancel.addEventListener("click", () => {
  state.pendingRequest = null;
  state.selectedActionId = null;
  clearPreview();
  elements.actionState.textContent = "等待输入";
});
elements.actionInput.addEventListener("input", () => {
  state.selectedActionId = null;
  clearPreview();
});
elements.retry.addEventListener("click", retryNarrative);
elements.toggleAudit.addEventListener("click", async () => {
  state.auditOpen = !state.auditOpen;
  elements.auditPanel.hidden = !state.auditOpen;
  elements.toggleAudit.setAttribute("aria-expanded", String(state.auditOpen));
  elements.toggleAudit.textContent = state.auditOpen ? "收起只读审计" : "查看只读审计";
  if (state.auditOpen) {
    try {
      await loadAudit();
    } catch (error) {
      elements.actionError.textContent = error.message;
    }
  }
});
elements.toggleTimeline.addEventListener("click", async () => {
  state.timelineOpen = !state.timelineOpen;
  elements.timelinePanel.hidden = !state.timelineOpen;
  elements.toggleTimeline.setAttribute("aria-expanded", String(state.timelineOpen));
  elements.toggleTimeline.textContent = state.timelineOpen ? "收起历史时间线" : "查看历史时间线";
  if (state.timelineOpen) {
    try {
      await loadTimeline();
    } catch (error) {
      elements.replayResult.textContent = `历史读取失败：${error.message}`;
    }
  }
});
elements.verifyLatest.addEventListener("click", () => verifyReplay());
document.querySelector("#copy-id").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(state.gameId);
    document.querySelector("#save-status").textContent = "编号已复制";
  } catch (error) {
    document.querySelector("#save-status").textContent = "请手动复制编号";
  }
});
document.querySelector("#return-entry").addEventListener("click", () => {
  elements.game.hidden = true;
  elements.entry.hidden = false;
  document.querySelector("#load-id").value = state.gameId;
});

// 页面刷新后尝试恢复上次存档；失败时保留手动读取入口。
const savedGameId = localStorage.getItem("grey-zone-game-id");
if (savedGameId) {
  loadGame(savedGameId).catch(() => {
    localStorage.removeItem("grey-zone-game-id");
    document.querySelector("#load-id").value = savedGameId;
  });
}

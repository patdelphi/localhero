/* 程序说明：连接本地 FastAPI，处理行动预览、确认提交、公开判定和只读审计。 */
"use strict";

const state = {
  gameId: null,
  selectedActionId: null,
  preview: null,
  pendingRequest: null,
  pendingNarrativeId: null,
  auditOpen: false,
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
};

const phaseLabels = {
  unoffered: "未接单",
  deferred: "委托暂缓",
  active: "调查中",
  closed: "已结案",
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
    if (event.payload.clues?.length) parts.push(`线索：${event.payload.clues.length} 条`);
    if (event.payload.ending) parts.push(`结局：${event.payload.ending}`);
    body.textContent = parts.join(" · ");
  } else {
    label.textContent = "场景";
    body.textContent = event.payload.text;
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
  document.querySelector("#case-ending").textContent = caseState.ending || "尚未结案";
  document.querySelector("#case-revision").textContent = caseState.revision;

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

async function loadGame(gameId) {
  const data = await api(`/api/games/${gameId}`);
  showGame(gameId);
  document.querySelector("#protagonist-name").textContent = data.game.protagonist;
  document.querySelector("#protagonist-mark").textContent = data.game.protagonist.slice(0, 1);
  document.querySelector("#roll-count").textContent = `${data.game.roll_count} 次`;
  renderCase(data.case);
  elements.sceneLog.replaceChildren(...data.events.map(renderEvent));
  elements.sceneLog.lastElementChild?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  if (state.auditOpen) await loadAudit();
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

document.querySelector("#new-game-form").addEventListener("submit", createGame);
document.querySelector("#load-game-form").addEventListener("submit", loadExistingGame);
document.querySelector("#action-form").addEventListener("submit", previewAction);
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
